import pytest

from cornac import create_app


@pytest.fixture(scope='session')
def app():
    return create_app()
