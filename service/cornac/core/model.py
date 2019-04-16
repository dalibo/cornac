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
    # Keep it sync with cornac/core/schema/001-instances.sql.
    'available',
    'backing-up',
    'creating',
    'deleting',
    'failed',
    'incompatible-network',
    'incompatible-option-group',
    'incompatible-parameters',
    'incompatible-restore',
    'maintenance',
    'modifying',
    'rebooting',
    'renaming',
    'resetting-master-credentials',
    'restore-error',
    'starting',
    'stopped',
    'stopping',
    'storage-full',
    'storage-optimization',
    'upgrading',
    name='db_instance_status',
)


class DBInstance(db.Model):
    __tablename__ = 'db_instances'

    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String)
    status = db.Column(DBInstanceStatus)
    status_message = db.Column(db.String)
    data = db.Column(JSONB)
    iaas_data = db.Column(JSONB)
    operator_data = db.Column(JSONB)

    def __str__(self):
        return f'instance #{self.id} {self.identifier} ({self.status})'
