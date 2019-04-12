import os

import pytest

from cornac import create_app


@pytest.fixture(scope='session')
def app():
    env = dict(
        os.environ,
        # Mock ssh key.
        CORNAC_DEPLOY_KEY='ssh-rsa dumb-deploy-key user@host',
    )
    return create_app(environ=env)
