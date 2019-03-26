from flask import current_app, make_response, request

from .rds import blueprint as rds


def fallback(e):
    # By default, log awscli requests.
    current_app.logger.info(
        "%s %s %s",
        request.method, request.path, dict(request.form))
    return make_response('Not Found', 404)


__all__ = ['fallback', 'rds']
