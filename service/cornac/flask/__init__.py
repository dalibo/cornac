import os.path

from flask import Flask


app = Flask(__name__)
config = app.config
config.from_object(__name__ + '.default_config')
if 'CORNAC_SETTINGS' in os.environ:
    path = os.path.realpath(os.environ['CORNAC_SETTINGS'])
    config.from_pyfile(path)


def create_app():
    from ..database.model import db
    db.init_app(app)
    return app
