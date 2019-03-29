import json
import logging
from contextlib import contextmanager
from time import sleep

import psycopg2


logger = logging.getLogger(__name__)
PGPASSWORD = 'C0nfidentiel'


@contextmanager
def pgconnect(instance, **kw):
    kw = dict(
        host=instance['Endpoint']['Address'],
        port=instance['Endpoint']['Port'],
        user=instance['MasterUsername'],
        dbname=instance['DBInstanceIdentifier'],
        **kw
    )
    with psycopg2.connect(**kw) as conn:
        with conn.cursor() as curs:
            yield curs


def wait_status(aws, wanted='available', instance='test0', first_delay=30):
    for s in range(first_delay, 1, -1):
        sleep(s)
        cmd = aws(
            "rds", "describe-db-instances",
            "--db-instance-identifier", instance)
        out = json.loads(cmd.stdout)
        if wanted == out['DBInstances'][0]['DBInstanceStatus']:
            break
    else:
        raise Exception("Timeout checking for status update.")


def test_describe_db_instances(aws, rds):
    cmd = aws("rds", "describe-db-instances")
    out = json.loads(cmd.stdout)
    assert 'cornac' == out['DBInstances'][0]['DBInstanceIdentifier']


def test_create_db_instance(aws, rds, worker):
    cmd = aws(
        "rds", "create-db-instance",
        "--db-instance-identifier", "test0",
        "--db-instance-class", "db.t2.micro",
        "--engine", "postgres",
        "--engine-version", "11",
        "--allocated-storage", "5",
        "--no-multi-az",
        "--master-username", "postgres",
        "--master-user-password", PGPASSWORD,
    )
    out = json.loads(cmd.stdout)
    assert 'creating' == out['DBInstance']['DBInstanceStatus']

    wait_status(aws, 'available')


def test_sql_to_endpoint(aws, rds):
    cmd = aws(
        "rds", "describe-db-instances", "--db-instance-identifier", "test0")
    out = json.loads(cmd.stdout)
    with pgconnect(out['DBInstances'][0], password=PGPASSWORD) as curs:
        curs.execute("SELECT NOW()")


def test_reboot_db_instance(aws, rds, worker):
    cmd = aws(
        "rds", "reboot-db-instance",
        "--db-instance-identifier", "test0",
    )
    out = json.loads(cmd.stdout)
    assert 'rebooting' == out['DBInstance']['DBInstanceStatus']

    wait_status(aws, 'available')

    with pgconnect(out['DBInstance'], password=PGPASSWORD) as curs:
        curs.execute("SELECT NOW()")


def test_delete_db_instance(aws, iaas, rds, worker):
    cmd = aws(
        "rds", "delete-db-instance",
        "--db-instance-identifier", "test0",
    )
    out = json.loads(cmd.stdout)
    assert 'deleting' == out['DBInstance']['DBInstanceStatus']

    for s in range(0, 60):
        sleep(s / 2.)
        try:
            cmd = aws(
                "rds", "describe-db-instances",
                "--db-instance-identifier", "test0")
            out = json.loads(cmd.stdout)
            if 'deleting' == out['DBInstances'][0]['DBInstanceStatus']:
                continue
        except Exception as e:
            logger.warning("Can't describe db instance anymore: %s", e)
            break
    else:
        raise Exception("Timeout deleting database instance.")

    assert 1 == len(list(iaas.list_machines()))
