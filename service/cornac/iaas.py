# API to manage machine, disks, networks, etc.
#

import logging
import shlex
import socket
import subprocess
from copy import deepcopy
from xml.etree import ElementTree as ET

import libvirt
import tenacity


logger = logging.getLogger(__name__)


class LibVirtConnection(object):
    # Context manager for libvirt.open().

    def __enter__(self):
        self.conn = libvirt.open()
        return self.conn

    def __exit__(self, *a):
        self.conn.close()


class LibVirtIaaS(object):
    # Uses libvirt binding, virt-manager and guestfs tools to manage VM.
    # Current purpose is PoC.

    def __init__(self, conn, config):
        self.conn = conn
        self.config = config
        # Configuration Keys:
        #
        # root_ssh_public_key: SSH public key to inject to access root account
        #                      on new machines.
        # dns_domain: DNS domain to build FQDN of machine on the IaaS.

    def create_machine(self, newname, origin):
        # The PoC reuses ressources until we have persistence of objects.
        try:
            domain = self.conn.lookupByName(newname)
        except libvirt.libvirtError:
            clone_cmd = [
                "virt-clone",
                "--original", origin,
                "--name", newname,
                "--auto-clone",
            ]
            logger.debug("Allocating machine.")
            logged_cmd(clone_cmd)
            domain = self.conn.lookupByName(newname)
        else:
            logger.debug("Reusing VM %s.", newname)

        state, _ = domain.state()
        if libvirt.VIR_DOMAIN_SHUTOFF == state:
            prepare_cmd = [
                "virt-sysprep",
                "--domain", newname,
                "--hostname", newname,
                "--selinux-relabel",
            ]
            if self.config['root_ssh_public_key']:
                prepare_cmd.extend([
                    "--ssh-inject",
                    f"root:string:{self.config['root_ssh_public_key']}",
                ])
            logger.debug("Preparing machine.")
            logged_cmd(prepare_cmd)

        return LibVirtMachine(name=newname, domain=domain)

    def create_disk(self, name, size):
        pool = self.conn.listAllStoragePools()[0]

        try:
            disk = pool.storageVolLookupByName(name)
        except libvirt.libvirtError:
            pass
        else:
            logger.debug("Reusing disk %s.", name)
            return disk

        # For now, just clone definition of first disk found in pool. Including
        # size.
        vol0 = pool.listAllVolumes()[0]
        oldxml = vol0.XMLDesc()
        newxml = oldxml.replace(vol0.name(), name)

        logger.debug("Creating disk %s.", name)
        return pool.createXML(newxml)

    def endpoint(self, machine):
        # Let's DNS resolve machine IP for now.
        return machine.name + self.config['dns_domain']


@tenacity.retry(wait=tenacity.wait_fixed(1),
                stop=tenacity.stop_after_delay(60),
                reraise=True)
def wait_machine(address, port=22):
    address = socket.gethostbyname(address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((address, port))
    sock.close()


class LibVirtMachine(object):
    def __init__(self, name, domain=None):
        self.name = name
        # libvirt handle
        self.domain = domain

    def attach_disk(self, disk):
        xml = self.domain.XMLDesc()
        path = disk.path()
        if path in xml:
            logger.debug("Disk %s already attached to %s.", path, self.name)
            return

        xml = ET.fromstring(xml)
        xdevices = xml.find('./devices')
        xdisk0 = xdevices.find('./disk')
        xdisk = deepcopy(xdisk0)
        xsrc = xdisk.find('./source')
        xsrc.attrib['file'] = path
        xtarget = xdisk.find('./target')
        xtarget.attrib['bus'] = 'scsi'
        xtarget.attrib['dev'] = 'sda'
        xdisk.remove(xdisk.find('./address'))
        # Try to place disk after first one.
        xdevices.insert(2, xdisk)

        xml = ET.tostring(xml, encoding="unicode")
        logger.debug("Attaching disk %s.", path)
        self.domain._conn.defineXML(xml)

    def start(self):
        state, _ = self.domain.state()
        if libvirt.VIR_DOMAIN_SHUTOFF == state:
            logger.debug("Starting %s.", self.name)
            self.domain.create()
        state, _ = self.domain.state()
        if libvirt.VIR_DOMAIN_RUNNING != state:
            raise Exception("%s is not running" % self.name)


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


class RemoteShell(object):
    def __init__(self, user, host):
        self.ssh = ["ssh", "-l", user, host]

    def __call__(self, command, raise_stdout=False):
        try:
            return logged_cmd(self.ssh + [shlex.quote(i) for i in command])
        except subprocess.CalledProcessError as e:
            # For bad script writing errors in stdout.
            raise Exception(e.stdout if raise_stdout else e.stderr)
