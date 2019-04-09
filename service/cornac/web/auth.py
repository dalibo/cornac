import logging
import re

from . import errors


logger = logging.getLogger(__name__)


def authenticate(request):
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

    return authorization.access_key


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

        kw = {}
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

    def __init__(self, access_key, algorithm, date, region_name, service_name,
                 signature, signed_headers, terminator):
        attrs = locals()
        del attrs['self']
        self.__dict__.update(attrs)
