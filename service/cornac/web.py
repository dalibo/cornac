import functools
import logging
import pdb
import sys
from concurrent.futures import ThreadPoolExecutor
from textwrap import dedent
from uuid import uuid4

from flask import Blueprint, abort, current_app, make_response, request
from jinja2 import Template

from .core.model import DBInstance, db
from .iaas import IaaS
from .operator import BasicOperator


logger = logging.getLogger(__name__)
rds = Blueprint('rds', __name__)


def fallback(e):
    # By default, log awscli requests.
    current_app.logger.info(
        "%s %s %s",
        request.method, request.path, dict(request.form))
    return make_response('Not Found', 404)


@rds.route("/rds", methods=["POST"])
def main():
    # Bridge RDS service and Flask routing. RDS actions are not RESTful.
    payload = dict(request.form)
    action_name = payload.pop('Action')

    try:
        action = getattr(RDS, action_name)
    except AttributeError:
        logger.warning("Unknown RDS action: %s.", action_name)
        logger.debug("payload=%r", payload)
        abort(400)

    return make_response_xml(
        action=action_name,
        result=action(payload),
        requestid=uuid4(),
    )


WORKERPOOL = ThreadPoolExecutor(max_workers=4)


def task(func):
    # Wraps a function to be executed in a concurrent executor for logging and
    # error handling.

    @functools.wraps(func)
    def task_wrapper(app, *a, **kw):
        logger.info("Running task %s.", func.__name__)
        try:
            with app.app_context():
                ret = func(*a, **kw)
            logger.info("Task %s done.", func.__name__)
            return ret
        except pdb.bdb.BdbQuit:
            pass
        except Exception:
            logger.exception("Unhandled exception in background task:")
            if False:
                pdb.post_mortem(sys.exc_info()[2])
            raise

    def send_task(*a, **kw):
        # Get effective current app, and pass it to wrapper. The wrapper will
        # set app as current app for the worker thread.
        app = current_app._get_current_object()
        WORKERPOOL.submit(task_wrapper, app, *a, **kw)

    task_wrapper.send = send_task

    return task_wrapper


@task
def create_db_task(instance_id):
    # Background task to trigger operator and update global in-memory database.

    instance = DBInstance.query.filter(DBInstance.id == instance_id).one()

    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        operator = BasicOperator(iaas, current_app.config)
        response = operator.create_db_instance(instance.create_command)

    instance.status = 'running'
    instance.attributes = response
    db.session.commit()


class RDS(object):
    # RDS-like service.
    #
    # Each method corresponds to a well-known RDS action, returning result as
    # XML snippet.

    default_create_command = dict(
        EngineVersion='11',
    )

    @classmethod
    def CreateDBInstance(cls, command):
        command = dict(cls.default_create_command, **command)
        command['AllocatedStorage'] = int(command['AllocatedStorage'])

        instance = DBInstance()
        instance.identifier = command['DBInstanceIdentifier']
        instance.status = 'creating'
        instance.create_command = command
        db.session.add(instance)
        db.session.commit()

        create_db_task.send(instance.id)

        return InstanceEncoder(instance).as_xml()

    INSTANCE_LIST_TMPL = Template(dedent("""\
    <DBInstances>
    {% for instance in instances %}
      {{ instance.as_xml() | indent(2) }}
    {% endfor %}
    </DBInstances>
    """), trim_blocks=True)

    @classmethod
    def DescribeDBInstances(cls, command):
        instances = DBInstance.query.all()
        return cls.INSTANCE_LIST_TMPL.render(
            instances=[InstanceEncoder(i) for i in instances])


RESPONSE_TMPL = Template("""\
<{{ action }}Response xmlns="http://rds.amazonaws.com/doc/2014-10-31/">
  <{{ action }}Result>
    {{ result | indent(4) }}
  </{{ action }}Result>
  <ResponseMetadata>
    <RequestId>{{ requestid }}</RequestId>
  </ResponseMetadata>
</{{ action }}Response>
""")


def make_response_xml(action, requestid, result):
    # Wraps result XML snippet in response XML envelope.

    xml = RESPONSE_TMPL.render(**locals())
    response = make_response(xml)
    response.content_type = 'text/xml; charset=utf-8'
    return response


class InstanceEncoder:
    # Adapt DBInstance object to RDS XML response.

    XML_SNIPPET_TMPL = Template(dedent("""\
    <DBInstance>
      <DBInstanceStatus>{{ status }}</DBInstanceStatus>
      <DBInstanceIdentifier>{{ identifier }}</DBInstanceIdentifier>
      <Engine>postgres</Engine>
    {% if endpoint_address %}
      <Endpoint>
        <Address>{{ endpoint_address }}</Address>
        <Port>5432</Port>
      </Endpoint>
    {% endif %}
      <MasterUsername>postgres</MasterUsername>
    </DBInstance>
    """), trim_blocks=True)

    def __init__(self, instance):
        self.instance = instance

    def as_xml(self):
        return self.XML_SNIPPET_TMPL.render(**self.instance.__dict__)
