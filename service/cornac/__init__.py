import os.path
from pathlib import Path
from pkg_resources import get_distribution
from warnings import filterwarnings

from flask import Flask


# psycopg2 and psycopg2-binary is a mess. You can't define OR dependency in
# Python. Just globally ignore this for now.
filterwarnings("ignore", message="The psycopg2 wheel package will be renamed")  # noqa


try:
    dist = get_distribution('pgCornac')
    __version__ = dist.version
except Exception:
    __version__ = 'unknown'


def create_app(environ=os.environ):

    app = Flask(__name__, instance_path=str(Path.home()))

    from .core.config import configure
    configure(app, environ=environ)

    from .core.model import db
    db.init_app(app)

    from .web import rds, fallback
    app.register_blueprint(rds)
    app.errorhandler(404)(fallback)

    from .worker import dramatiq
    dramatiq.init_app(app)

    return app
