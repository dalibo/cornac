import logging

from flask_dramatiq import Dramatiq
from dramatiq_pg import PostgresBroker
from psycopg2.pool import ThreadedConnectionPool


dramatiq = Dramatiq()
logger = logging.getLogger(__name__)


class URLPostgresBroker(PostgresBroker):
    def __init__(self, url):
        super(URLPostgresBroker, self).__init__(
            pool=ThreadedConnectionPool(0, 16, url))
