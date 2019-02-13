import logging
import os
import pdb
import sys
from urllib.parse import urlparse

import click

from .iaas import IaaS
from .operator import BasicOperator
from .utils import KnownError


logger = logging.getLogger(__name__)


@click.group()
def root(argv=sys.argv[1:]):
    pass


@root.command()
def bootstrap():
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
