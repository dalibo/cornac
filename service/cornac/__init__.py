import os.path
from warnings import filterwarnings

from flask import Flask


# psycopg2 and psycopg2-binary is a mess. You can't define OR dependency in
# Python. Just globally ignore this for now.
filterwarnings("ignore", message="The psycopg2 wheel package will be renamed")  # noqa


def create_app(environ=os.environ):

    app = Flask(__name__)

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
