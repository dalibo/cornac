#
# Main cornac CLI.
#
# Implements few commands for cornac initialization and maintainance. Running
# the webservice is distinct since Flask already provide a good CLI for
# development and production should use WSGI entrypoint.
#

import logging
import os
import pdb
import sys
from textwrap import dedent
from urllib.parse import urlparse

import click
from flask.cli import FlaskGroup


from .database import connect
from .database.migrator import Migrator
from .database.model import DBInstance
from .iaas import IaaS
from .operator import BasicOperator
from .utils import KnownError


logger = logging.getLogger(__name__)


def create_app():
    # Fake factory for Flask app.
    from .flask import app
    return app


# Root group of CLI.
@click.group(cls=FlaskGroup, create_app=create_app)
def root(argv=sys.argv[1:]):
    pass


@root.command(help=dedent(
    """
    Provision guest and Postgres database for cornac itself. Initialize
    database with schema and data.
    """))
@click.option('--pgversion', default='11',
              help="Postgres engine version to deploy.",
              show_default=True, metavar='VERSION')
@click.option('--size', default=5, type=click.IntRange(5, 300),
              help="Allocated storage size in gigabytes.",
              show_default=True, metavar='SIZE_GB',)
@click.pass_context
def bootstrap(ctx, pgversion, size):
    from .flask import app, db

    connstring = app.config['SQLALCHEMY_DATABASE_URI']
    pgurl = urlparse(connstring)
    command = dict(
        AllocatedStorage=size,
        DBInstanceIdentifier=pgurl.path.lstrip('/'),
        Engine='postgres',
        EngineVersion=pgversion,
        MasterUserPassword=pgurl.password,
        MasterUsername=pgurl.username,
    )
    logger.info("Creating instance %s.", command['DBInstanceIdentifier'])
    with IaaS.connect(app.config['IAAS'], app.config) as iaas:
        operator = BasicOperator(iaas, app.config)
        operator.create_db_instance(command)

    logger.info("Initializing schema.")
    ctx.invoke(migratedb, dry=False)

    logger.info("Registering instance to inventory.")
    with app.app_context():
        instance = DBInstance()
        instance.identifier = command['DBInstanceIdentifier']
        instance.status = 'running'
        # Drop master password before saving command in database.
        instance.create_params = dict(command, MasterUserPassword=None)
        db.session.add(instance)
        db.session.commit()
    logger.debug("Done")


@root.command(help="Migrate schema and database of cornac database.")
@click.option('--dry/--no-dry', default=True,
              help="Whether to effectively apply migration script.")
def migratedb(dry):
    from .flask import app

    migrator = Migrator()
    migrator.inspect_available_versions()
    with connect(app.config['SQLALCHEMY_DATABASE_URI']) as conn:
        migrator.inspect_current_version(conn)
        if migrator.current_version:
            logger.info("Database version is %s.", migrator.current_version)
        else:
            logger.info("Database is not initialized.")

        versions = migrator.missing_versions
        for version in versions:
            if dry:
                logger.info("Would apply %s.", version)
            else:
                logger.info("Applying %s.", version)
                with conn:  # Wraps in a transaction.
                    migrator.apply(conn, version)

    if versions:
        logger.info("Check terminated." if dry else "Database updated.")
    else:
        logger.info("Database already uptodate.")


def entrypoint():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)1.1s: %(message)s',
    )

    try:
        exit(root())
    except (pdb.bdb.BdbQuit, KeyboardInterrupt):
        logger.info("Interrupted.")
    except KnownError as e:
        logger.critical("%s", e)
        exit(e.exit_code)
    except Exception:
        logger.exception('Unhandled error:')
        if sys.stdout.isatty():
            logger.debug("Dropping in debugger.")
            pdb.post_mortem(sys.exc_info()[2])
        else:
            logger.error(
                "Please report at "
                "https://github.com/dalibo/cornac/issues/new with full log.",
            )
    exit(os.EX_SOFTWARE)
