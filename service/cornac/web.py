import functools
import logging
import pdb
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from textwrap import dedent
from uuid import uuid4

from flask import abort, make_response, request
from jinja2 import Template

from .iaas import IaaS
from .operator import BasicOperator


# Setup logging before instanciating Flask app.
logging.basicConfig(format="%(levelname)5.5s %(message)s", level=logging.DEBUG)
from .app import app  # noqa
logger = logging.getLogger(__name__)

# Fake in-memory database.
INSTANCES = OrderedDict()


@app.errorhandler(404)
def fallback(e):
    # By default, log awscli requests.
    app.logger.info(
        "%s %s %s",
        request.method, request.path, dict(request.form))
    return make_response('Not Found', 404)


@app.route("/", methods=["POST"])
def main():
    # Bridge RDS service and Flask routing. RDS actions are not RESTful.
    payload = dict(request.form)
    action_name = payload.pop('Action')

    try:
        action = getattr(RDS, action_name)
    except AttributeError:
        logger.warning("Unknown RDS action: %s.", action_name)
        abort(400)

    return make_response_xml(
        action=action_name,
        result=action(payload),
        requestid=uuid4(),
    )


def task(func):
    # Wraps a function to be executed in a concurrent executor for logging and
    # error handling.

    @functools.wraps(func)
    def task_wrapper(*a, **kw):
        logger.info("Running task %s.", func.__name__)
        try:
            return func(*a, **kw)
        except pdb.bdb.BdbQuit:
            pass
        except Exception:
            logger.exception("Unhandled exception in background task:")
            if False:
                pdb.post_mortem(sys.exc_info()[2])
            raise

    return task_wrapper


@task
def create_db_task(command):
    # Background task to trigger operator and update global in-memory database.

    if command['DBInstanceIdentifier'] not in INSTANCES:
        raise Exception("Unknown instance")

    with IaaS.connect(app.config['IAAS'], app.config) as iaas:
        operator = BasicOperator(iaas, app.config)
        response = operator.create_db_instance(command)

    instance = INSTANCES[command['DBInstanceIdentifier']]
    instance.status = 'running'
    instance.endpoint_address = response['Endpoint']['Address']


class RDS(object):
    # RDS-like service.
    #
    # Each method corresponds to a well-known RDS action, returning result as
    # XML snippet.

    workerpool = ThreadPoolExecutor(max_workers=4)
    default_create_command = dict(
        EngineVersion='11',
    )

    @classmethod
    def CreateDBInstance(cls, command):
        instance = DBInstance(
            identifier=command['DBInstanceIdentifier'],
            status='creating',
        )
        INSTANCES[instance.identifier] = instance
        command = dict(cls.default_create_command, **command)
        command['AllocatedStorage'] = int(command['AllocatedStorage'])
        cls.workerpool.submit(create_db_task, command)
        return instance.as_xml()

    INSTANCE_LIST_TMPL = Template(dedent("""\
    <DBInstances>
    {% for instance in instances %}
      {{ instance.as_xml() | indent(2) }}
    {% endfor %}
    </DBInstances>
    """), trim_blocks=True)

    @classmethod
    def DescribeDBInstances(cls, command):
        return cls.INSTANCE_LIST_TMPL.render(instances=INSTANCES.values())


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


class DBInstance(object):
    # This object helps tracking instance status in memory and rendering
    # instance object to XML response.

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

    def __init__(self, identifier, status):
        self.identifier = identifier
        self.status = status
        self.endpoint_address = None

    def as_xml(self):
        return self.XML_SNIPPET_TMPL.render(**self.__dict__)
