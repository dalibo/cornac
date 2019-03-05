import os.path

from flask import Flask


def create_app():
    app = Flask('cornac')

    app.config.from_object(__name__ + '.default_config')
    if 'CORNAC_SETTINGS' in os.environ:
        path = os.path.realpath(os.environ['CORNAC_SETTINGS'])
        app.config.from_pyfile(path)

    from ..database.model import db
    db.init_app(app)

    return app
