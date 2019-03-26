import logging
from textwrap import dedent
from uuid import uuid4

from flask import Blueprint, abort, current_app, make_response, request
from jinja2 import Template
from werkzeug.exceptions import HTTPException

from . import worker
from .core.model import DBInstance, db


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
    identifier = payload.get('DBInstanceIdentifier', '-')
    requestid = uuid4()
    log_args = ("RDS %s %s", action_name, identifier)

    try:
        action = getattr(RDS, action_name, None)
        if action is None:
            logger.warning("Unknown RDS action: %s.", action_name)
            logger.debug("payload=%r", payload)
            raise InvalidAction()

        response = make_response_xml(
            action=action_name,
            result=action(payload),
            requestid=requestid,
        )
        current_app.logger.info(*log_args)
    except HTTPException as e:
        current_app.logger.error(*log_args)
        if not isinstance(e, RDSError):
            e = RDSError(code=e.code, description=str(e))
        response = make_error_xml(error=e, requestid=requestid)
    except Exception:
        current_app.logger.exception(*log_args)
        # Don't expose error.
        response = make_error_xml(error=RDSError(), requestid=requestid)

    return response


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
        instance.data = command
        db.session.add(instance)
        db.session.commit()

        worker.create_db.send(instance.id)

        return InstanceEncoder(instance).as_xml()

    @classmethod
    def DeleteDBInstance(cls, command):
        instance = (
            DBInstance.query
            .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
            .one())
        instance.status = 'deleting'
        worker.delete_db_instance.send(instance.id)
        db.session.commit()
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
        qry = DBInstance.query
        if 'DBInstanceIdentifier' in command:
            qry = qry.filter(
                DBInstance.identifier == command['DBInstanceIdentifier'])
        instances = qry.all()
        return cls.INSTANCE_LIST_TMPL.render(
            instances=[InstanceEncoder(i) for i in instances])

    @classmethod
    def RebootDBInstance(cls, command):
        instance = (
            DBInstance.query
            .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
            .one())
        instance.status = 'rebooting'
        db.session.commit()
        worker.reboot_db_instance.send(instance.id)
        return InstanceEncoder(instance).as_xml()

    @classmethod
    def StartDBInstance(cls, command):
        instance = (
            DBInstance.query
            .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
            .one())
        instance.status = 'starting'
        db.session.commit()
        worker.start_db_instance.send(instance.id)
        return InstanceEncoder(instance).as_xml()

    @classmethod
    def StopDBInstance(cls, command):
        instance = (
            DBInstance.query
            .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
            .one())
        instance.status = 'stopping'
        db.session.commit()
        worker.stop_db_instance.send(instance.id)
        return InstanceEncoder(instance).as_xml()


class RDSError(HTTPException):
    code = 500
    description = (
        'The request processing has failed because of an unknown error, '
        'exception or failure.')
    rdscode = 'InternalFailure'

    def __init__(self, code=None, rdscode=None, **kw):
        super().__init__(**kw)
        if code:
            self.code = code
        if rdscode:
            self.rdscode = rdscode


ERROR_TMPL = Template("""\
<ErrorResponse>
   <Error>
      <Type>{{ type }}</Type>
      <Code>{{ rdscode }}</Code>
      <Message>{{ message }}</Message>
   </Error>
   <RequestId>{{ requestid }}</RequestId>
</ErrorResponse>
""")


def make_error_xml(error, requestid):
    xml = ERROR_TMPL.render(
        code=error.code,
        message=error.description,
        rdscode=error.rdscode,
        requestid=requestid,
        type='Sender' if error.code < 500 else 'Receiver',
    )
    response = make_response(xml)
    response.status_code = error.code
    response.content_type = 'text/xml; charset=utf-8'
    return response


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
        try:
            endpoint_address = self.instance.data['Endpoint']['Address']
        except (KeyError, TypeError):
            endpoint_address = None
        return self.XML_SNIPPET_TMPL.render(
            endpoint_address=endpoint_address,
            **self.instance.__dict__,
        )


class InvalidAction(RDSError):
    code = 400
    description = (
        'The action or operation requested is invalid. '
        'Verify that the action is typed correctly.')
    rdscode = 'InvalidAction'
