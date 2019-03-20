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
def app():
    app = create_app()
    with app.app_context():
        yield app


@pytest.fixture(scope='session', autouse=True)
def clean_vms(iaas):
    yield None
    if 'KEEP' in os.environ:
        return
    for machine in iaas.list_machines():
        iaas.delete_machine(machine)


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
def rds():
    proc = Popen(["cornac", "--verbose", "run"])
    http_wait('http://localhost:5000/rds')
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
def worker():
    proc = Popen([
        "cornac", "--verbose", "worker",
        "--processes=1", "--threads=2",
    ])
    try:
        yield proc
    finally:
        proc.terminate()
        proc.communicate()
