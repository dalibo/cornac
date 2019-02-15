import logging
import shlex
import socket
import subprocess

import tenacity


logger = logging.getLogger(__name__)


def logged_cmd(cmd, *a, **kw):
    logger.debug("Running %s", ' '.join([shlex.quote(i) for i in cmd]))
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
    stop=tenacity.stop_after_delay(300),
    reraise=True)


@remote_retry
def wait_machine(address, port=22):
    address = socket.gethostbyname(address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((address, port))
    sock.close()


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
                [shlex.quote(i) for i in command],
            )
        except subprocess.CalledProcessError as e:
            # SSH shows stderr in stdout.
            raise Exception(e.stdout)

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
