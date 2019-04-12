import os.path
from warnings import filterwarnings

from flask import Flask


# psycopg2 and psycopg2-binary is a mess. You can't define OR dependency in
# Python. Just globally ignore this for now.
filterwarnings("ignore", message="The psycopg2 wheel package will be renamed")  # noqa


def filter_env(config, environ=os.environ):
    known_vars = set(f'CORNAC_{k}' for k in config)
    return dict(
        (k.replace('CORNAC_', ''), v)
        for k, v in environ.items()
        if k in known_vars)


def create_app(environ=os.environ):
    app = Flask(__name__)
    app.config.from_object(__name__ + '.core.config.defaults')
    if 'CORNAC_SETTINGS' in os.environ:
        path = os.path.realpath(os.environ['CORNAC_SETTINGS'])
        app.config.from_pyfile(path)

    c = app.config
    c.from_mapping(filter_env(c, environ=environ))
    if not c['DRAMATIQ_BROKER_URL']:
        c['DRAMATIQ_BROKER_URL'] = c['SQLALCHEMY_DATABASE_URI']

    from .core.model import db
    db.init_app(app)

    from .web import rds, fallback
    app.register_blueprint(rds)
    app.errorhandler(404)(fallback)

    from .worker import dramatiq
    dramatiq.init_app(app)

    return app
