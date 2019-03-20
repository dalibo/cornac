import logging

from flask import current_app
from flask_dramatiq import Dramatiq
from dramatiq_pg import PostgresBroker
from psycopg2.pool import ThreadedConnectionPool

from .core.model import DBInstance, db
from .iaas import IaaS
from .operator import BasicOperator
from .ssh import wait_machine


dramatiq = Dramatiq()
logger = logging.getLogger(__name__)


class URLPostgresBroker(PostgresBroker):
    def __init__(self, url):
        super(URLPostgresBroker, self).__init__(
            pool=ThreadedConnectionPool(0, 16, url))


@dramatiq.actor
def create_db(instance_id):
    instance = DBInstance.query.filter(DBInstance.id == instance_id).one()

    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        operator = BasicOperator(iaas, current_app.config)
        response = operator.create_db_instance(instance.data)

    instance.status = 'available'
    instance.data = dict(
        instance.data,
        # Drop password from data.
        MasterUserPassword=None,
        **response,
    )
    db.session.commit()


@dramatiq.actor
def delete_db_instance(instance_id):
    instance = DBInstance.query.get(instance_id)
    if instance is None:
        return logger.warn("Unknown instance #%s. Deleted ?", instance_id)

    logger.info("Deleting %s.", instance)
    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        iaas.delete_machine(instance.identifier)
    db.session.delete(instance)
    db.session.commit()


@dramatiq.actor
def start_db_instance(instance_id):
    instance = DBInstance.query.get(instance_id)
    logger.info("Starting %s.", instance)
    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        iaas.start_machine(instance.identifier)
    wait_machine(instance.data['Endpoint']['Address'])
    instance.status = 'available'
    db.session.commit()


@dramatiq.actor
def stop_db_instance(instance_id):
    instance = DBInstance.query.get(instance_id)
    logger.info("Stopping %s.", instance)
    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        iaas.stop_machine(instance.identifier)
    instance.status = 'stopped'
    db.session.commit()
