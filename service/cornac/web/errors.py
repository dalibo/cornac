from werkzeug.exceptions import HTTPException


class RDSError(HTTPException):
    code = 500
    description = (
        'The request processing has failed because of an unknown error, '
        'exception or failure.')
    rdscode = 'InternalFailure'

    def __init__(self, code=None, rdscode=None, **kw):
        super().__init__(**kw)
        if code:
            self.code = code
        if rdscode:
            self.rdscode = rdscode

    @classmethod
    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        cls.rdscode = cls.__name__


class DBInstanceAlreadyExists(RDSError):
    code = 400
    description = 'DB Instance already exists'


class DBInstanceNotFound(RDSError):
    code = 404

    def __init__(self, identifier):
        super().__init__(description=f"DBInstance {identifier} not found.")


class IncompleteSignature(RDSError):
    code = 400


class InvalidAction(RDSError):
    code = 400
    description = (
        'The action or operation requested is invalid. '
        'Verify that the action is typed correctly.')


class InvalidClientTokenId(RDSError):
    code = 403
    description = 'The security token included in the request is invalid.'


class MissingAuthenticationToken(RDSError):
    code = 403
    description = 'Missing Authentication Token'
