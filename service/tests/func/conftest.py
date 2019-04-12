import json
import logging
import os
import sys
from functools import partial
from pathlib import Path
from subprocess import Popen
from time import sleep

import pytest
import requests.exceptions
from sh import aws as awscli

from cornac import create_app
from cornac.iaas import IaaS


logger = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def app(cornac_env):
    app = create_app(environ=cornac_env)
    with app.app_context():
        yield app


class AWSCLI(object):
    def __init__(self, cli):
        self.cli = cli

    def __call__(self, *a, **kw):
        return self.cli(*a, **kw)

    def wait_status(self, wanted='available', instance='test0',
                    first_delay=30):
        for s in range(first_delay, 1, -1):
            sleep(s)
            cmd = self.cli(
                "rds", "describe-db-instances",
                "--db-instance-identifier", instance)
            out = json.loads(cmd.stdout)
            if wanted == out['DBInstances'][0]['DBInstanceStatus']:
                break
        else:
            raise Exception("Timeout checking for status update.")


@pytest.fixture(scope='session')
def aws(cornac_env):
    awscli_config = Path(__file__).parent.parent / 'awscli-config'
    aws_env = dict(
        cornac_env,
        AWS_CONFIG_FILE=str(awscli_config / 'config'),
        AWS_PROFILE='local',
        AWS_SHARED_CREDENTIALS_FILE=str(awscli_config / 'credentials')
    )
    yield AWSCLI(partial(awscli, _env=aws_env))


@pytest.fixture(scope='session', autouse=True)
def clean_vms(iaas):
    yield None
    if 'KEEP' in os.environ:
        return
    for machine in iaas.list_machines():
        logger.info("Deleting %s.", machine)
        iaas.delete_machine(machine)


@pytest.fixture(scope='session')
def cornac_env():
    preserved_vars = set((
        'CORNAC_DNS_DOMAIN',
        'CORNAC_IAAS',
        'CORNAC_NETWORK',
        'CORNAC_ORIGINAL_MACHINE',
        'CORNAC_ROOT_PUBLIC_KEY',
        'CORNAC_STORAGE_POOL',
        'CORNAC_VCENTER_RESOURCE_POOL',
    ))

    # Generate a clean environment for cornac commands.
    clean_environ = dict(
        (k, v) for k, v in os.environ.items()
        if k in preserved_vars or
        (not k.startswith('AWS_') and
         not k.startswith('PG') and
         not k.startswith('CORNAC_'))
    )
    # Reuse local prefix.
    prefix = 'test' + os.environ.get('CORNAC_MACHINE_PREFIX', 'cornac-')
    # Overwrite PG conninfo accordingly.
    dns_domain = os.environ.get('CORNAC_DNS_DOMAIN', '')
    db = 'cornac'
    conninfo = f"postgresql://cornac:1EstP4ss@{prefix}{db}{dns_domain}/{db}"
    return dict(
        clean_environ,
        CORNAC_CONFIG=str(Path(__file__).parent.parent / 'cornac-config.py'),
        CORNAC_MACHINE_PREFIX=prefix,
        CORNAC_SQLALCHEMY_DATABASE_URI=conninfo,
    )


def http_wait(url):
    for _ in range(32):
        try:
            return requests.get(url)
        except requests.exceptions.ConnectionError:
            sleep(.1)
        except Exception as e:
            return e
    else:
        raise Exception("Failed to start HTTP server on time.")


@pytest.fixture(scope='session')
def iaas(app):
    with IaaS.connect(app.config['IAAS'], app.config) as iaas:
        yield iaas


@pytest.fixture(scope='session')
def rds(cornac_env):
    # Ensure no other cornac is running.
    try:
        requests.get('http://localhost:5000/rds')
        raise Exception("cornac web already running.")
    except requests.exceptions.RequestException:
        pass

    proc = Popen(["cornac", "--verbose", "serve"], env=cornac_env)
    http_wait('http://localhost:5000/rds')

    # Ensure cornac is effectively running.
    if proc.poll():
        raise Exception("Failed to start cornac web.")

    try:
        yield proc
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture(autouse=True)
def reset_logs(caplog, capsys):
    logging.getLogger('sh').setLevel(logging.ERROR)
    caplog.clear()
    capsys.readouterr()


def lazy_write(attr, data):
    # Lazy access sys.{stderr,stdout} to mix with capsys.
    return getattr(sys, attr).write(data)


@pytest.fixture(scope='session', autouse=True)
def sh_errout():
    import sh
    sh._SelfWrapper__self_module.Command._call_args.update(dict(
        err=partial(lazy_write, 'stderr'),
        out=partial(lazy_write, 'stdout'),
        tee=True,
    ))


@pytest.fixture(scope='session')
def worker(cornac_env):
    proc = Popen([
        "cornac", "--verbose", "worker",
        "--processes=1", "--threads=2",
    ], env=cornac_env)
    try:
        yield proc
    finally:
        proc.terminate()
        proc.communicate()
