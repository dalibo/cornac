import logging

from flask import current_app
from flask_dramatiq import Dramatiq
from dramatiq_pg import PostgresBroker
from psycopg2.pool import ThreadedConnectionPool

from .core.model import DBInstance, db
from .iaas import IaaS
from .operator import BasicOperator


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
        response = operator.create_db_instance(instance.create_command)

    instance.status = 'running'
    instance.attributes = response
    db.session.commit()
