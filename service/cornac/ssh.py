import logging
import shlex
import socket
import subprocess
from random import randint

import tenacity

from .errors import RemoteCommandError


logger = logging.getLogger(__name__)


def logged_cmd(cmd, *a, **kw):
    logger.debug("Running %s", ' '.join([shlex.quote(str(i)) for i in cmd]))
    # Unpack passwords now that command is logged.
    cmd = [a.password if isinstance(a, Password) else a for a in cmd]
    child = subprocess.Popen(
        cmd, *a, **kw,
        stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    err = []
    for line in child.stderr:
        line = line.strip().decode('utf-8')
        err.append(line)
        logger.debug("<<< %s", line)
    out = child.stdout.read().decode('utf-8')
    returncode = child.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=returncode,
            cmd=cmd,
            output=out,
            stderr='\n'.join(err),
        )
    return out


remote_retry = tenacity.retry(
    wait=tenacity.wait_chain(*[
        tenacity.wait_fixed(i) for i in range(12, 1, -1)
    ]),
    retry=(tenacity.retry_if_exception_type(RemoteCommandError) |
           tenacity.retry_if_exception_type(OSError)),
    stop=tenacity.stop_after_delay(300),
    reraise=True)


@remote_retry
def wait_machine(address, port=22):
    address = socket.gethostbyname(address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((address, port))
    sock.close()


class Password(object):
    seed = randint(0, 1000)

    def __init__(self, password):
        self.password = password
        self.hash_ = hash(f"{self.seed}-{self.password}")

    def __repr__(self):
        return '<%s %x>' % (self.__class__.__name__, self.hash_)

    def __str__(self):
        return '********'


class RemoteShell(object):
    ssh_options = [
        # For now, just accept any key from remote hosts.
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "StrictHostKeyChecking=no",
    ]

    def __init__(self, user, host):
        self.ssh = ["ssh", "-q", "-l", user, host]
        self.scp_target_prefix = f"{user}@{host}:"

    def __call__(self, command):
        try:
            return logged_cmd(
                self.ssh + self.ssh_options +
                [
                    Password(shlex.quote(i.password))
                    if isinstance(i, Password) else
                    shlex.quote(i)
                    for i in command
                ],
            )
        except subprocess.CalledProcessError as e:
            # SSH shows commands stderr in stdout and SSH client logs in
            # stderr, let's make it clear.
            message = e.stdout or e.stderr
            if message:
                message = message.splitlines()[-1]
            else:
                message = "Unknown error."
            raise RemoteCommandError(
                message=message,
                exit_code=e.returncode,
                ssh_logs=e.stderr)

    def copy(self, src, dst):
        try:
            return logged_cmd(
                ["scp"] + self.ssh_options +
                [src, self.scp_target_prefix + dst]
            )
        except subprocess.CalledProcessError as e:
            raise Exception(e.stderr)

    @remote_retry
    def wait(self):
        # Just ping with true to trigger SSH. This method allows Host rewrite
        # in ssh_config.
        self(["true"])
