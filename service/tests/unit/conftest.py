import pytest

from cornac import create_app


@pytest.fixture
def app():
    return create_app()
