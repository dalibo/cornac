import logging
from functools import partial
from uuid import uuid4

from flask import Blueprint, current_app, g, request
from werkzeug.exceptions import HTTPException

from . import (
    actions,
    errors,
    xml,
)
from .auth import authenticate


blueprint = Blueprint('rds', __name__)
logger = logging.getLogger(__name__)


def log(requestid, action_name, identifier, result, code=200,
        level=logging.INFO, access_key='-'):
    # Composable helper for request logging.
    current_app.logger.log(
        level, "RDS %s %s %s %s %s",
        access_key, action_name, identifier, code, result)


@blueprint.route("/rds", methods=["POST"])
def main():
    # Bridge RDS service and Flask routing. RDS actions are not RESTful.
    payload = dict(request.form.items(multi=False))
    action_name = payload.pop('Action')
    version = payload.pop('Version')
    identifier = payload.get('DBInstanceIdentifier', '-')
    requestid = uuid4()
    log_ = partial(log, requestid, action_name, identifier)

    try:
        if version != '2014-10-31':
            raise errors.InvalidAction(
                description=f"Unsupported API version {version}.")
        g.access_key = authenticate(request)
        log_ = partial(log_, access_key=g.access_key)
        action = getattr(actions, action_name, None)
        if action is None:
            logger.warning("Unknown RDS action: %s.", action_name)
            logger.debug("payload=%r", payload)
            raise errors.InvalidAction()

        response = xml.make_response_xml(
            action=action_name,
            result=action(**payload),
            requestid=requestid,
        )
        log_(result='OK')
    except HTTPException as e:
        if not isinstance(e, errors.RDSError):
            e = errors.RDSError(code=e.code, description=str(e))
        # Still log user error at INFO level.
        log_(code=e.code, result=e.rdscode)
        response = xml.make_error_xml(error=e, requestid=requestid)
    except Exception:
        # Don't expose error.
        e = errors.RDSError()
        current_app.logger.exception("Unhandled RDS error:")
        log_(code=e.code, result=e.rdscode, level=logging.ERROR)
        response = xml.make_error_xml(error=e, requestid=requestid)

    return response
