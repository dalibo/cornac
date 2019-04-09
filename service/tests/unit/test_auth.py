import pytest
from flask import request


def test_missing_token(app):
    from cornac.web.rds import authenticate, errors

    with app.test_request_context():
        with pytest.raises(errors.MissingAuthenticationToken):
            authenticate(request)

    with app.test_request_context(headers=[('Authorization', 'malformed')]):
        with pytest.raises(errors.MissingAuthenticationToken):
            authenticate(request)

    minimal = 'algo Credential=k/d/rg/rds/term, SignedHeaders=X, Signature=X'

    with app.test_request_context(headers=[('Authorization', minimal)]):
        with pytest.raises(errors.InvalidClientTokenId):
            authenticate(request, credentials=dict(key='notsecret'))


def test_parse_authorization():
    from cornac.web.auth import Authorization, errors

    raw = (
        'AWS4-HMAC-SHA256 '
        'Credential=AKIAIO46HSYHYN/20190409/eu-west-3/rds/aws4_request, '
        'SignedHeaders=content-type;host;x-amz-date, '
        'Signature=7313b609a8f3f794d9408c4a4a2327b9a2e8ffdc3ecb47')

    value = Authorization.parse(raw)
    assert 'AWS4-HMAC-SHA256' == value.algorithm
    assert 'AKIAIO46HSYHYN' == value.access_key
    assert '20190409' == value.date
    assert 'eu-west-3' == value.region_name
    assert 'rds' == value.service_name
    assert 'aws4_request' == value.terminator
    assert ['content-type', 'host', 'x-amz-date'] == value.signed_headers
    assert '7313b609a8f3f794d9408c4a4a2327b9a2e8ffdc3ecb47' == value.signature

    raw = (
        'AWS4-HMAC-SHA256 '
        'Credential=AKIAIO46HSYHYN/20190409/eu-west-3/rds/aws4_request, '
        'SignedHeaders=content-type;host;x-amz-date, ')

    with pytest.raises(errors.IncompleteSignature):
        Authorization.parse(raw)
