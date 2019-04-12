# RDS-like service.
#
# Each method corresponds to a well-known RDS action, returning result as
# XML snippet.

import logging
from datetime import datetime
from textwrap import dedent

from jinja2 import Template
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

from . import (
    errors,
    xml,
)
from .. import worker
from ..core.model import DBInstance, db


logger = logging.getLogger(__name__)
DEFAULT_CREATE_COMMAND = dict(
    EngineVersion='11',
    MultiAZ='false',
)


def get_instance(identifier):
    try:
        return (
            DBInstance.query
            .filter(DBInstance.identifier == identifier)
            .one())
    except NoResultFound:
        raise errors.DBInstanceNotFound(identifier)


def check_create_command(command):
    command = dict(DEFAULT_CREATE_COMMAND, **command)
    command['AllocatedStorage'] = int(command['AllocatedStorage'])
    command['MultiAZ'] = command['MultiAZ'] == 'true'
    if command['MultiAZ']:
        raise errors.InvalidParameterCombination(
            "Multi-AZ instance is not yet supported.")
    now = datetime.utcnow()
    command['InstanceCreateTime'] = now.isoformat(timespec='seconds') + 'Z'
    return command


def CreateDBInstance(**command):
    command = check_create_command(command)

    instance = DBInstance()
    instance.identifier = command['DBInstanceIdentifier']
    instance.status = 'creating'
    instance.data = command
    db.session.add(instance)
    try:
        db.session.commit()
    except IntegrityError:
        raise errors.DBInstanceAlreadyExists()

    worker.create_db.send(instance.id)

    return xml.InstanceEncoder(instance).as_xml()


def DeleteDBInstance(*, DBInstanceIdentifier, **command):
    instance = get_instance(DBInstanceIdentifier)
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


def DescribeDBInstances(**command):
    qry = DBInstance.query
    if 'DBInstanceIdentifier' in command:
        qry = qry.filter(
            DBInstance.identifier == command['DBInstanceIdentifier'])
    instances = qry.all()
    return INSTANCE_LIST_TMPL.render(
        instances=[xml.InstanceEncoder(i) for i in instances])


def RebootDBInstance(*, DBInstanceIdentifier):
    instance = (
        DBInstance.query
        .filter(DBInstance.identifier == DBInstanceIdentifier)
        .one())
    instance.status = 'rebooting'
    db.session.commit()
    worker.reboot_db_instance.send(instance.id)
    return xml.InstanceEncoder(instance).as_xml()


def StartDBInstance(*, DBInstanceIdentifier):
    instance = get_instance(DBInstanceIdentifier)
    instance.status = 'starting'
    db.session.commit()
    worker.start_db_instance.send(instance.id)
    return xml.InstanceEncoder(instance).as_xml()


def StopDBInstance(DBInstanceIdentifier):
    instance = get_instance(DBInstanceIdentifier)
    instance.status = 'stopping'
    db.session.commit()
    worker.stop_db_instance.send(instance.id)
    return xml.InstanceEncoder(instance).as_xml()
