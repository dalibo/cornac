import logging
import os
import pdb
import sys
from urllib.parse import urlparse

import click

from .database import connect
from .database.migrator import Migrator
from .iaas import IaaS
from .operator import BasicOperator
from .utils import KnownError


logger = logging.getLogger(__name__)


@click.group()
def root(argv=sys.argv[1:]):
    pass


@root.command()
@click.pass_context
def bootstrap(ctx):
    from .app import app

    connstring = app.config['DATABASE']
    pgurl = urlparse(connstring)
    command = dict(
        AllocatedStorage=5,
        DBInstanceIdentifier=pgurl.path.lstrip('/'),
        Engine='postgres',
        EngineVersion='11',
        MasterUserPassword=pgurl.password,
        MasterUsername=pgurl.username,
    )
    logger.info("Creating instance %s.", command['DBInstanceIdentifier'])
    with IaaS.connect(app.config['IAAS'], app.config) as iaas:
        operator = BasicOperator(iaas, app.config)
        operator.create_db_instance(command)

    logger.info("Initializing schema.")
    ctx.forward(migratedb, dry=False)

    # Now we could register user, instance, etc.


@root.command()
@click.option('--dry/--no-dry', default=True,
              help="Whether to effectively apply migration script.")
def migratedb(dry):
    from .app import app

    migrator = Migrator()
    migrator.inspect_available_versions()
    with connect(app.config['DATABASE']) as conn:
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
