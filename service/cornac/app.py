import os.path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
config = app.config
config.from_object('cornac.default_config')
if 'CORNAC_SETTINGS' in os.environ:
    path = os.path.realpath(os.environ['CORNAC_SETTINGS'])
    config.from_pyfile(path)
db = SQLAlchemy(app)
