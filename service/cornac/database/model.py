from sqlalchemy.dialects.postgresql import (
    ENUM,
    JSONB,
)

from ..flask import db


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
