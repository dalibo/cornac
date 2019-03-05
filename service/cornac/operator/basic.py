# Apply actions on infrastructure.
#
# The concept of Operator is borrowed from K8S.
#

import logging
import pdb
import sys
from pathlib import Path

from ..iaas import IaaS
from ..ssh import RemoteShell


logger = logging.getLogger(__name__)


class BasicOperator(object):
    # Implementation using pghelper.sh

    def __init__(self, iaas, config):
        self.iaas = iaas
        self.config = config
        # Configuration keys:
        #
        # original_machine: name of the template machine with Postgres.

    def create_db_instance(self, command):
        name = f"cornac-{command['DBInstanceIdentifier']}"
        machine = self.iaas.create_machine(
            name=name,
            storage_pool=self.config['STORAGE_POOL'],
            data_size_gb=command['AllocatedStorage'],
        )
        self.iaas.start(machine)
        address = self.iaas.endpoint(machine)
        shell = RemoteShell('root', address)
        shell.wait()
        logger.debug("Sending helper script.")
        local_helper = str(Path(__file__).parent / 'pghelper.sh')
        helper = '/usr/local/bin/pghelper.sh'
        shell.copy(local_helper, helper)

        # Formatting disk
        try:
            # Check whether Postgres VG is configured.
            shell(["test", "-d", "/dev/Postgres"])
        except Exception:
            dev = self.iaas.guess_data_device_in_guest(machine)
            shell([helper, "prepare-disk", dev])
            shell([
                helper, "create-instance",
                command['EngineVersion'],
                command['DBInstanceIdentifier'],
            ])
            shell([helper, "start"])
        else:
            logger.debug("Reusing Postgres instance.")

        # Master user
        master = command['MasterUsername']
        shell([
            helper,
            "create-masteruser", master, command['MasterUserPassword'],
        ])

        # Creating database
        bases = shell([helper, "psql", "-l"])
        dbname = command['DBInstanceIdentifier']
        if f"\n {dbname} " in bases:
            logger.debug("Reusing database %s.", dbname)
        else:
            logger.debug("Creating database %s.", dbname)
            shell([helper, "create-database", dbname, master])

        return dict(
            Endpoint=dict(Address=address, Port=5432),
            DBInstanceIdentifier=dbname,
        )


def test_main():
    # Hard coded real test case, for PoC development.

    from .. import config

    # What aws would send to REST API.
    command = {
        'DBInstanceIdentifier': 'cli0',
        'AllocatedStorage': 5,
        'DBInstanceClass': 'db.t2.micro',
        'Engine': 'postgres',
        'EngineVersion': '11',
        'MasterUsername': 'postgres',
        'MasterUserPassword': 'C0nfidentiel',
    }

    with IaaS.connect(config['IAAS'], config) as iaas:
        operator = BasicOperator(iaas, config)
        response = operator.create_db_instance(command)

    logger.info(
        "    psql -h %s -p %s -U %s -d %s",
        response['Endpoint']['Address'],
        response['Endpoint']['Port'],
        command['MasterUsername'],
        command['DBInstanceIdentifier'],
    )


if "__main__" == __name__:
    logging.basicConfig(
        format="%(levelname)5.5s %(message)s",
        level=logging.DEBUG,
    )

    try:
        test_main()
    except pdb.bdb.BdbQuit:
        pass
    except Exception:
        logger.exception("Uhandled error:")
        pdb.post_mortem(sys.exc_info()[2])
