import os.path
from warnings import filterwarnings

from flask import Flask


# psycopg2 and psycopg2-binary is a mess, because you can't define OR
# dependency in Python. Just globally ignore this for now.
filterwarnings("ignore", message="The psycopg2 wheel package will be renamed")  # noqa


def create_app():
    app = Flask(__name__)

    app.config.from_object(__name__ + '.default_config')
    if 'CORNAC_SETTINGS' in os.environ:
        path = os.path.realpath(os.environ['CORNAC_SETTINGS'])
        app.config.from_pyfile(path)

    from .core.model import db
    db.init_app(app)

    return app
