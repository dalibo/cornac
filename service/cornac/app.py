import os

from flask import Flask


app = Flask(__name__)
config = app.config
config.from_object('cornac.default_config')
if 'CORNAC_SETTINGS' in os.environ:
    path = os.getcwd() + '/' + os.environ['CORNAC_SETTINGS']
    config.from_pyfile(path)
