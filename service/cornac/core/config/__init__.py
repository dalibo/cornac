import logging
import os
import subprocess

from flask import current_app

from cornac.errors import KnownError


logger = logging.getLogger(__name__)


def configure(app, environ=os.environ):
    app.config.from_object(__name__ + '.defaults')

    c = app.config
    c.from_mapping(filter_env(c, environ=environ))

    pathes = app.config['CONFIG'].split(',')
    for path in pathes:
        path = os.path.realpath(path)
        if os.path.exists(path):
            app.config.from_pyfile(path)

    if not c['DRAMATIQ_BROKER_URL']:
        c['DRAMATIQ_BROKER_URL'] = c['SQLALCHEMY_DATABASE_URI']

    if not c['DEPLOY_KEY'] and 'SSH_AUTH_SOCK' in environ:
        c['DEPLOY_KEY'] = read_ssh_key()


def filter_env(config, environ=os.environ):
    known_vars = set(f'CORNAC_{k}' for k in config)
    return dict(
        (k.replace('CORNAC_', ''), v)
        for k, v in environ.items()
        if k in known_vars)


def read_ssh_key():
    logger.debug("Reading SSH keys from agent.")
    try:
        out = subprocess.check_output(["ssh-add", "-L"])
    except Exception as e:
        raise KnownError(f"Failed to read SSH public key: {e}") from None

    keys = out.decode('utf-8').splitlines()
    if keys:
        return keys[0]


def require_ssh_key():
    if not current_app.config['CONFIG']:
        raise KnownError("SSH Agent has no key loaded.")
