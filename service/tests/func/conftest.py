import os
import sys
from functools import partial
from subprocess import Popen
from time import sleep

import pytest
import requests.exceptions

from cornac import create_app
from cornac.iaas import IaaS


@pytest.fixture(scope='session')
def app(cornac_env):
    app = create_app(environ=cornac_env)
    with app.app_context():
        yield app


@pytest.fixture(scope='session', autouse=True)
def clean_vms(iaas):
    yield None
    if 'KEEP' in os.environ:
        return
    for machine in iaas.list_machines():
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
        (not k.startswith('CORNAC_') and not k.startswith('PG'))
    )
    # Reuse local prefix.
    prefix = 'test' + os.environ.get('CORNAC_MACHINE_PREFIX', 'cornac-')
    # Overwrite PG conninfo accordingly.
    dns_domain = os.environ.get('CORNAC_DNS_DOMAIN', '')
    db = 'cornac'
    conninfo = f"postgresql://cornac:1EstP4ss@{prefix}{db}{dns_domain}/{db}"
    return dict(
        clean_environ,
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
