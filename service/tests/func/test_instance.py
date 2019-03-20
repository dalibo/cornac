import json
import logging
from time import sleep

import psycopg2
from sh import aws


logger = logging.getLogger(__name__)


def test_describe_db_instances(rds):
    cmd = aws("rds", "describe-db-instances")
    out = json.loads(cmd.stdout)
    assert 'cornac' == out['DBInstances'][0]['DBInstanceIdentifier']


def test_create_db_instance(rds, worker):
    cmd = aws(
        "rds", "create-db-instance",
        "--db-instance-identifier", "test0",
        "--db-instance-class", "db.t2.micro",
        "--engine", "postgres",
        "--engine-version", "11",
        "--allocated-storage", "5",
        "--no-multi-az",
        "--master-username", "postgres",
        "--master-user-password", "C0nfidentiel",
    )
    out = json.loads(cmd.stdout)
    assert 'creating' == out['DBInstance']['DBInstanceStatus']

    for s in range(25, 1, -1):  # This waits up to 325s
        sleep(s)
        cmd = aws(
            "rds", "describe-db-instances",
            "--db-instance-identifier", "test0")
        out = json.loads(cmd.stdout)
        if 'available' == out['DBInstances'][0]['DBInstanceStatus']:
            break
    else:
        raise Exception("Timeout creating database instance.")


def test_sql_to_endpoint(rds):
    cmd = aws(
        "rds", "describe-db-instances", "--db-instance-identifier", "test0")
    out = json.loads(cmd.stdout)
    instance, = out['DBInstances']
    pgconn = psycopg2.connect(
        host=instance['Endpoint']['Address'],
        port=instance['Endpoint']['Port'],
        user=instance['MasterUsername'],
        password='C0nfidentiel',
    )
    with pgconn:
        with pgconn.cursor() as curs:
            curs.execute("SELECT NOW()")


def test_delete_db_instance(rds, worker):
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
            if 'continue' == out['DBInstances'][0]['DBInstanceStatus']:
                continue
        except Exception as e:
            logger.warning("Can't describe db instance anymore: %s", e)
            break
    else:
        raise Exception("Timeout deleting database instance.")
