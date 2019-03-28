import os


class KnownError(Exception):
    def __init__(self, message, exit_code=os.EX_SOFTWARE):
        super(KnownError, self).__init__(message)
        self.exit_code = exit_code


class RemoteCommandError(Exception):
    def __init__(self, message, exit_code, ssh_logs):
        super().__init__(message)
        self.exit_code = exit_code
        self.ssh_logs = ssh_logs


class Timeout(Exception):
    pass
