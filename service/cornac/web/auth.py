import copy
import logging
import re
from datetime import datetime

from botocore.auth import SigV4Auth, SIGV4_TIMESTAMP, ISO8601
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from flask import current_app
from werkzeug.urls import url_encode

from . import errors


logger = logging.getLogger(__name__)


def authenticate(request, credentials=None):
    if credentials is None:
        credentials = current_app.config['CREDENTIALS']

    try:
        authorization = request.headers['Authorization']
    except KeyError:
        raise errors.MissingAuthenticationToken()

    try:
        authorization = Authorization.parse(authorization)
    except Exception as e:
        logger.debug(
            "Failed to parse Authorization header: %.40s: %s.",
            authorization, e)
        raise errors.MissingAuthenticationToken()

    try:
        secret_key = credentials[authorization.access_key]
    except KeyError:
        raise errors.InvalidClientTokenId()

    check_request_signature(
        request,
        authorization, secret_key=secret_key,
        region=current_app.config['REGION'])

    return authorization.access_key


def check_request_signature(request, authorization, secret_key,
                            region='local'):
    # Reuse botocore API to validate signature.
    if 'AWS4-HMAC-SHA256' != authorization.algorithm:
        raise errors.IncompleteSignature(
            f"Unsupported AWS 'algorithm': '{authorization.algorithm}'")

    if 'aws4_request' != authorization.terminator:
        raise errors.SignatureDoesNotMatch(
            "Credential should be scoped with a valid terminator: "
            f"'aws4_request', not '{authorization.terminator}'.")

    if 'host' not in authorization.signed_headers:
        raise errors.SignatureDoesNotMatch(
            "'Host' must be a 'SignedHeader' in the AWS Authorization.")

    headers_key = {k.lower() for k in request.headers.keys()}
    headers_to_sign = set(authorization.signed_headers)
    for h in headers_to_sign:
        if h not in headers_key:
            raise errors.SignatureDoesNotMatch(
                f"Authorization header requires existence of '{h}' header. "
                f"{authorization}")

    creds = Credentials(authorization.access_key, secret_key)
    signer = SigV4Auth(creds, 'rds', region)
    awsrequest = make_boto_request(request, headers_to_sign)
    canonical_request = signer.canonical_request(awsrequest)
    string_to_sign = signer.string_to_sign(awsrequest, canonical_request)
    signature = signer.signature(string_to_sign, awsrequest)

    if signature != authorization.signature:
        raise errors.SignatureDoesNotMatch(description=(
            "The request signature we calculated does not match the signature "
            "you provided. Check your AWS Secret Access Key and signing "
            "method. Consult the service documentation for details."
        ))


def make_boto_request(request, headers_to_sign=None):
    # Adapt a Flask request object to AWSRequest.

    if headers_to_sign is None:
        headers_to_sign = [h.lower() for h in request.headers.keys()]
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() in headers_to_sign}

    awsrequest = AWSRequest(
        method=request.method,
        url=request.url,
        headers=headers,
        # Re-encode back form data. Flask loose it :/ We may want to subclass
        # Flask/Werkzeug Request class to keep the raw_data value before
        # decoding form-data. Say, only if content-length is below 1024 bytes.
        data=url_encode(request.form, 'utf-8'),
    )

    # Get sig timestamp from headers.
    if 'x-amz-date' in request.headers:
        timestamp = request.headers['X-Amz-Date']
    elif 'date' in request.headers:
        date = datetime.strptime(ISO8601, request.headers['Date'])
        timestamp = date.strftime(SIGV4_TIMESTAMP, date)
    else:
        raise errors.IncompleteSignature(
            "Authorization header requires existence of either "
            "'X-Amz-Date' or 'Date' header. "
            f"{request.headers['Authorization']}")
    awsrequest.context['timestamp'] = timestamp

    return awsrequest


class Authorization(object):
    _parameter_re = re.compile(r'([A-Za-z]+)=([^, ]*)')

    @classmethod
    def parse(cls, raw):
        # raw is Authorization header value as bytes, in the following format:
        #
        #     <algorithm> Credential=<access_key>/<date>/<region>/<service>/aws4_request, SignedHeaders=<header0>;<header1>;…, Signature=xxx  # noqa
        #
        # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-auth-using-authorization-header.html
        # explains details.

        kw = dict(raw=raw)
        kw['algorithm'], parameters = raw.split(maxsplit=1)

        missing_parameters = {'Credential', 'SignedHeaders', 'Signature'}
        for match in cls._parameter_re.finditer(parameters):
            key, value = match.groups()
            if key in missing_parameters:
                missing_parameters.remove(key)
            if 'Credential' == key:
                value = value.split('/')
                access_key, date, region_name, service_name, terminator = value
                kw.update(
                    access_key=access_key,
                    date=date,
                    region_name=region_name,
                    service_name=service_name,
                    terminator=terminator
                )
            elif 'SignedHeaders' == key:
                kw['signed_headers'] = value.split(';')
            elif 'Signature' == key:
                kw['signature'] = value

        if missing_parameters:
            raise errors.IncompleteSignature(
                ' '.join(
                    f"Authorization header requires '{k}'parameter."
                    for k in missing_parameters) +
                f'Authorization={raw}'
            )

        return cls(**kw)

    def __init__(self, *, access_key, algorithm='AWS4-HMAC-SHA256', date,
                 region_name='local', service_name='rds',
                 signature, signed_headers='host', terminator='aws4_request',
                 raw=None):
        attrs = locals()
        del attrs['self']
        self.__dict__.update(attrs)

    def __str__(self):
        if self.raw is None:
            scope = "/".join([
                self.access_key, self.date, self.region_name,
                self.service_name, self.terminator,
            ])
            signed_headers = ';'.join(self.signed_headers)
            self.raw = (
                f"{self.algorithm} "
                f"Credential={scope}, "
                f"SignepdHeaders={signed_headers}, "
                f"Signature={self.signature}"
            )
        return self.raw

    def __setattr__(self, name, value):
        # Note that self.__dict__.update() bypasses __setattr__.
        if name != 'raw':
            # Invalidate serialization cache.
            self.raw = None
        return super().__setattr__(name, value)

    def copy(self, **kw):
        clone = copy.deepcopy(self)
        clone.__dict__.update(kw)
        return clone
