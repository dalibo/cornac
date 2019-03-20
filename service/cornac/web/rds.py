import logging
from uuid import uuid4

from flask import Blueprint, current_app, request
from werkzeug.exceptions import HTTPException

from . import (
    actions,
    errors,
    xml,
)


blueprint = Blueprint('rds', __name__)
logger = logging.getLogger(__name__)


@blueprint.route("/rds", methods=["POST"])
def main():
    # Bridge RDS service and Flask routing. RDS actions are not RESTful.
    payload = dict(request.form)
    action_name = payload.pop('Action')
    payload.pop('Version')
    identifier = payload.get('DBInstanceIdentifier', '-')
    requestid = uuid4()
    log_args = ("RDS %s %s %s", requestid, action_name, identifier)

    try:
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
        current_app.logger.info(*log_args)
    except HTTPException as e:
        current_app.logger.error(*log_args)
        if not isinstance(e, errors.RDSError):
            e = errors.RDSError(code=e.code, description=str(e))
        response = xml.make_error_xml(error=e, requestid=requestid)
    except Exception:
        current_app.logger.exception(*log_args)
        # Don't expose error.
        e = errors.RDSError()
        response = xml.make_error_xml(error=e, requestid=requestid)

    return response
