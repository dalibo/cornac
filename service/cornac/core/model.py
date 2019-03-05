from contextlib import contextmanager

import psycopg2
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import (
    ENUM,
    JSONB,
)


db = SQLAlchemy()


@contextmanager
def connect(connstring):
    # Manager for connecting to psycopg2 without flask nor SQLAlchemy.
    conn = psycopg2.connect(connstring)
    try:
        yield conn
    finally:
        conn.close()


DBInstanceStatus = ENUM(
    'creating',
    'running',
    'stopped',
    name='db_instance_status',
)


class DBInstance(db.Model):
    __tablename__ = 'db_instances'

    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String)
    status = db.Column(DBInstanceStatus)
    status_message = db.Column(db.String)
    create_command = db.Column(JSONB)
    attributes = db.Column(JSONB)
