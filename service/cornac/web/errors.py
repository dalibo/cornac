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


class InvalidAction(RDSError):
    code = 400
    description = (
        'The action or operation requested is invalid. '
        'Verify that the action is typed correctly.')
    rdscode = 'InvalidAction'
