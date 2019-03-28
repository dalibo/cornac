#
# Main cornac CLI.
#
# Implements few commands for cornac initialization and maintainance. Running
# the webservice is distinct since Flask already provide a good CLI for
# development and production should use WSGI entrypoint.
#

import errno
import logging.config
import os
import pdb
import sys
from textwrap import dedent
from urllib.parse import urlparse

import bjoern
import click
from flask import current_app
from flask.cli import FlaskGroup
from sqlalchemy.exc import IntegrityError


from . import create_app
from .core.model import DBInstance, db, connect
from .core.schema import Migrator
from .errors import KnownError
from .iaas import IaaS
from .operator import BasicOperator
from .ssh import wait_machine


logger = logging.getLogger(__name__)


class CornacGroup(FlaskGroup):
    # Wrapper around FlaskGroup to lint error handling.

    def main(self, *a, **kw):
        try:
            return super().main(*a, **kw)
        except OSError as e:
            if errno.EADDRINUSE == e.errno:
                raise KnownError("Address already in use.")
            raise


# Root group of CLI.
@click.group(cls=CornacGroup, create_app=create_app)
@click.option('--verbose/-v', default=False)
@click.pass_context
def root(ctx, verbose):
    appname = ctx.invoked_subcommand or 'cornac'
    setup_logging(appname=appname, verbose=verbose)


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
    connstring = current_app.config['SQLALCHEMY_DATABASE_URI']
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
    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        operator = BasicOperator(iaas, current_app.config)
        operator.create_db_instance(command)

    logger.info("Creating schema.")
    ctx.invoke(migratedb, dry=False)

    logger.info("Registering own instance to inventory.")
    instance = DBInstance()
    instance.identifier = command['DBInstanceIdentifier']
    instance.status = 'available'
    # Drop master password before saving command in database.
    instance.create_params = dict(command, MasterUserPassword=None)
    db.session.add(instance)
    try:
        db.session.commit()
    except IntegrityError:
        logger.debug("Already registered.")
    else:
        logger.debug("Done")


@root.command(help="Serve on HTTP for production.")
@click.argument('listen', default='')
def serve(listen):
    host, _, port = listen.partition(':')
    host = host or 'localhost'
    port = int(port or 5000)
    app = current_app._get_current_object()
    logger.info("Serving on http://%s:%s/.", host, port)
    bjoern.run(app, host, port)


@root.command(help="Migrate schema and database of cornac database.")
@click.option('--dry/--no-dry', default=True,
              help="Whether to effectively apply migration script.")
def migratedb(dry):
    migrator = Migrator()
    migrator.inspect_available_versions()
    with connect(current_app.config['SQLALCHEMY_DATABASE_URI']) as conn:
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


@root.command(help="Ensure Cornac service VM are up.")
def recover():
    with IaaS.connect(current_app.config['IAAS'], current_app.config) as iaas:
        iaas.start_machine('cornac')
    connstring = current_app.config['SQLALCHEMY_DATABASE_URI']
    pgurl = urlparse(connstring)
    port = pgurl.port or 5432
    logger.info("Waiting for %s:%s opening.", pgurl.hostname, port)
    wait_machine(pgurl.hostname, port=port)
    logger.info("Testing PostgreSQL connection.")
    with connect(connstring):
        pass
    logger.info("Cornac is ready to run.")


def entrypoint():
    debug = os.environ.get('DEBUG', '').lower() in ('1', 'y')
    setup_logging(verbose=debug)

    try:
        exit(root())
    except (pdb.bdb.BdbQuit, KeyboardInterrupt):
        logger.info("Interrupted.")
    except KnownError as e:
        logger.critical("%s", e)
        exit(e.exit_code)
    except Exception:
        logger.exception('Unhandled error:')
        if debug and sys.stdout.isatty():
            logger.debug("Dropping in debugger.")
            pdb.post_mortem(sys.exc_info()[2])
        else:
            logger.error(
                "Please report at "
                "https://github.com/dalibo/cornac/issues/new with full log.",
            )
    exit(os.EX_SOFTWARE)


def setup_logging(*, appname='cornac', verbose):
    format = '%(levelname)1.1s: %(message)s'
    if verbose:
        format = f'%(asctime)s {appname}[%(process)s] {format}'

    config = {
        'version': 1,
        'formatters': {
            'default': {
                '()': 'logging.Formatter',
                'format': format,
                'datefmt': '%H:%M:%S',
            },
        },
        'handlers': {
            'default': {
                '()': 'logging.StreamHandler',
                'formatter': 'default',
            },
        },
        'root': {
            'level': 'INFO',
            'handlers': ['default'],
        },
        'loggers': {
            __package__: {
                'level': logging.DEBUG if verbose else logging.INFO,
            },
        },
    }
    logging.config.dictConfig(config)
