import logging

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
    @classmethod
    def parse(cls, raw):
        # raw is Authorization header value as bytes, in the following format:
        #
        #     <algorithm> Credential=<access_key>/<date>/<region>/<service>/aws4_request, SignedHeaders=<header0>;<header1>;…, Signature=xxx  # noqa
        #
        # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-auth-using-authorization-header.html
        # explains details.

        algorithm, values = raw.split(maxsplit=1)
        credential, signed_headers, signature = values.split(',')
        _, credential = credential.strip().split('=')
        credential = credential.split('/')
        access_key, date, region_name, service_name, terminator = credential
        _, signed_headers = signed_headers.strip().split('=')
        signed_headers = signed_headers.split(';')
        _, signature = signature.strip().split('=')
        return cls(
            access_key=access_key,
            algorithm=algorithm,
            date=date,
            region_name=region_name,
            service_name=service_name,
            signature=signature,
            signed_headers=signed_headers,
            terminator=terminator,
        )

    def __init__(self, access_key, algorithm, date, region_name, service_name,
                 signature, signed_headers, terminator):
        attrs = locals()
        del attrs['self']
        self.__dict__.update(attrs)
