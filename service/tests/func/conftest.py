import os

import pytest

from cornac import create_app
from cornac.iaas import IaaS


@pytest.fixture(scope='session')
def app():
    app = create_app()
    with app.app_context():
        yield app


@pytest.fixture(scope='session')
def iaas(app):
    with IaaS.connect(app.config['IAAS'], app.config) as iaas:
        yield iaas


@pytest.fixture(scope='session', autouse=True)
def clean_vms(iaas):
    yield None
    if 'KEEP' in os.environ:
        return
    for machine in iaas.list_machines():
        iaas.delete_machine(machine)
