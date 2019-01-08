import subprocess


def make_poc_config():
    # Simple, hard-coded configuration for PoC purpose.

    ssh_keys = subprocess.check_output(["ssh-add", "-L"])
    ssh_key = ssh_keys.splitlines()[0].decode('utf-8')

    return dict(
        dns_domain='.virt',
        original_machine='base-cornac',
        root_ssh_public_key=ssh_key,
    )
