import pytest
from flask import request


def test_missing_token(app):
    from cornac.web.rds import authenticate, errors

    with app.test_request_context():
        with pytest.raises(errors.MissingAuthenticationToken):
            authenticate(request)

    with app.test_request_context(headers=[('Authorization', 'pouet')]):
        authenticate(request)
