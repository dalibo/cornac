# Apply actions on infrastructure.
#
# The concept of Operator is borrowed from K8S.
#

import json
import logging
import pdb
import sys


from .config import make_poc_config
from .iaas import (
    LibVirtConnection,
    LibVirtIaaS,
    RemoteShell,
    wait_machine,
)


logger = logging.getLogger(__name__)


_1G = 1024 * 1024 * 1024


class SocleOperator(object):
    # Implementation using Dalibo Python scripts and a IaaS.

    def __init__(self, iaas, config):
        self.iaas = iaas
        self.config = config
        # Configuration keys:
        #
        # original_machine: name of the template machine with Postgres and
        #                   Dalibo's scripts installed.

    def create_db_instance(self, command):
        name = f"cornac-{command['DBInstanceIdentifier']}"
        origin = self.config['original_machine']
        machine = self.iaas.create_machine(newname=name, origin=origin)
        storage_pool = self.iaas.get_pool(self.config['storage_pool'])
        disk = storage_pool.create_disk(
            name=f'{name}-data.qcow2',
            size=int(command['AllocatedStorage'] * _1G),
        )
        machine.attach_disk(disk)
        machine.start()
        address = self.iaas.endpoint(machine)
        wait_machine(address)
        shell = RemoteShell('root', address)

        # Creating instance
        try:
            shell(["test", "-d", "/var/lib/pgsql/11/main/data_mnt/data/"])
        except Exception:
            pass
            input_json = dict(
                backup_password="C0nfidentiel",
                replication_password="C0nfidentiel",
                superuser_password=command["MasterUserPassword"],
            )
            shell([
                "create_instance.py", "/dev/sda", "--force",
                "--input-json", json.dumps(input_json),
                "--surole-in-pgpass",
            ], raise_stdout=True)
        else:
            logger.debug("Reusing Postgres instance.")

        # Creating database
        supg = ["sudo", "-u", "postgres"]
        bases = shell(supg + ["psql", "-l"])
        dbname = command['DBInstanceIdentifier']
        if f"\n {dbname} " in bases:
            logger.debug("Reusing database %s.", dbname)
        else:
            logger.debug("Creating database %s.", dbname)
            shell(
                supg + ["create_database.py", dbname, "--force"],
                raise_stdout=True,
            )

        # Allowing connect from any IP.
        shell(supg + [
            "alter_role.py", "postgres", dbname,
            "--version=11", "--client-ips=0.0.0.0/0",
        ], raise_stdout=True)

        return dict(
            Endpoint=dict(Address=address, Port=5432),
            DBInstanceIdentifier=dbname,
        )


def test_main():
    # Hard coded real test case, for PoC development.

    config = make_poc_config()
    # What aws would send to REST API.
    command = {
        'DBInstanceIdentifier': 'cli0',
        'AllocatedStorage': 5,
        'DBInstanceClass': 'db.t2.micro',
        'Engine': 'postgres',
        'MasterUsername': 'postgres',
        'MasterUserPassword': 'C0nfidentiel',
    }

    with LibVirtConnection() as conn:
        iaas = LibVirtIaaS(conn, config)
        operator = SocleOperator(iaas, config)
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
