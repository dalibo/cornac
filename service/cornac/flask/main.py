import logging


def create_app():
    from . import app
    __import__('cornac.web')
    return app


# Setup logging before instanciating Flask app.
logging.basicConfig(format="%(levelname)5.5s %(message)s", level=logging.DEBUG)
app = create_app()
