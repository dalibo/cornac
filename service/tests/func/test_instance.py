import json
from time import sleep

from sh import aws


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
