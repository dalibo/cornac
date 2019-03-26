# RDS-like service.
#
# Each method corresponds to a well-known RDS action, returning result as
# XML snippet.

from textwrap import dedent

from jinja2 import Template

from . import xml
from .. import worker
from ..core.model import DBInstance, db


DEFAULT_CREATE_COMMAND = dict(
    EngineVersion='11',
)


def CreateDBInstance(command):
    command = dict(DEFAULT_CREATE_COMMAND, **command)
    command['AllocatedStorage'] = int(command['AllocatedStorage'])

    instance = DBInstance()
    instance.identifier = command['DBInstanceIdentifier']
    instance.status = 'creating'
    instance.data = command
    db.session.add(instance)
    db.session.commit()

    worker.create_db.send(instance.id)

    return xml.InstanceEncoder(instance).as_xml()


def DeleteDBInstance(command):
    instance = (
        DBInstance.query
        .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
        .one())
    instance.status = 'deleting'
    worker.delete_db_instance.send(instance.id)
    db.session.commit()
    return xml.InstanceEncoder(instance).as_xml()


INSTANCE_LIST_TMPL = Template(dedent("""\
<DBInstances>
{% for instance in instances %}
  {{ instance.as_xml() | indent(2) }}
{% endfor %}
</DBInstances>
"""), trim_blocks=True)


def DescribeDBInstances(command):
    qry = DBInstance.query
    if 'DBInstanceIdentifier' in command:
        qry = qry.filter(
            DBInstance.identifier == command['DBInstanceIdentifier'])
    instances = qry.all()
    return INSTANCE_LIST_TMPL.render(
        instances=[xml.InstanceEncoder(i) for i in instances])


def RebootDBInstance(command):
    instance = (
        DBInstance.query
        .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
        .one())
    instance.status = 'rebooting'
    db.session.commit()
    worker.reboot_db_instance.send(instance.id)
    return xml.InstanceEncoder(instance).as_xml()


def StartDBInstance(command):
    instance = (
        DBInstance.query
        .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
        .one())
    instance.status = 'starting'
    db.session.commit()
    worker.start_db_instance.send(instance.id)
    return xml.InstanceEncoder(instance).as_xml()


def StopDBInstance(command):
    instance = (
        DBInstance.query
        .filter(DBInstance.identifier == command['DBInstanceIdentifier'])
        .one())
    instance.status = 'stopping'
    db.session.commit()
    worker.stop_db_instance.send(instance.id)
    return xml.InstanceEncoder(instance).as_xml()
