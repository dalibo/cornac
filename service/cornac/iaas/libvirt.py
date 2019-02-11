# API to manage machine, disks, networks, etc.
#

import logging
import os
from copy import deepcopy
from string import ascii_lowercase
from xml.etree import ElementTree as ET

import libvirt

from . import IaaS
from cornac.ssh import logged_cmd


logger = logging.getLogger(__name__)


class LibVirtDisk(object):
    def __init__(self, handle):
        self.handle = handle
        self.machine = None

    def guess_device_on_guest(self):
        # Guess /dev/disk/by-path/… device file from XML.
        xml = self.machine.domain.XMLDesc()
        xml = ET.fromstring(xml)
        xdiskaddress = xml.find(
            f".//disk/source[@file='{self.handle.path()}']/../address")
        xcontrolleraddress = xml.find(
            ".//controller[@type='scsi']/address[@type='pci']")
        pci_path = 'pci-{domain:04d}:{bus:02d}:{slot:02d}.{function}'.format(
            bus=int(xcontrolleraddress.attrib['bus'], base=0),
            domain=int(xcontrolleraddress.attrib['domain'], base=0),
            function=int(xcontrolleraddress.attrib['function'], base=0),
            slot=int(xcontrolleraddress.attrib['slot'], base=0),
        )
        # cf.
        # https://cgit.freedesktop.org/systemd/systemd/tree/src/udev/udev-builtin-path_id.c#n405
        scsi_path = 'scsi-{controller}:{bus}:{target}:{unit}'.format(
            **xdiskaddress.attrib)
        return f'/dev/disk/by-path/{pci_path}-{scsi_path}'


class LibVirtIaaS(IaaS):
    # Uses libvirt binding, virt-manager and guestfs tools to manage VM.
    # Current purpose is PoC.

    @classmethod
    def connect(cls, url, config):
        return cls(libvirt.open(), config)

    def __init__(self, conn, config):
        self.conn = conn
        self.config = config
        # Configuration Keys:
        #
        # root_ssh_public_key: SSH public key to inject to access root account
        #                      on new machines.
        # dns_domain: DNS domain to build FQDN of machine on the IaaS.

    def close(self):
        self.conn.close()

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
            if self.config['ROOT_PUBLIC_KEY']:
                prepare_cmd.extend([
                    "--ssh-inject",
                    f"root:string:{self.config['ROOT_PUBLIC_KEY']}",
                ])
            logger.debug("Preparing machine.")
            logged_cmd(prepare_cmd)

        return LibVirtMachine(name=newname, domain=domain)

    def get_pool(self, name):
        return LibVirtStoragePool(self.conn.storagePoolLookupByName(name))

    def endpoint(self, machine):
        # Let's DNS resolve machine IP for now.
        return machine.name + self.config['DNS_DOMAIN']


class LibVirtMachine(object):
    def __init__(self, name, domain=None):
        self.name = name
        # libvirt handle
        self.domain = domain

    def attach_disk(self, disk):
        xml = self.domain.XMLDesc()
        path = disk.handle.path()
        disk.machine = self
        if path in xml:
            logger.debug("Disk %s already attached to %s.", path, self.name)
            return

        xml = ET.fromstring(xml)
        xdevices = xml.find('./devices')
        xdisk0 = xdevices.find('./disk')
        xdisk = deepcopy(xdisk0)
        xsrc = xdisk.find('./source')
        xsrc.attrib['file'] = path
        xscsitargets = xml.findall(".//disk/target[@bus='scsi']")
        devs = [e.attrib['dev'] for e in xscsitargets]
        xtarget = xdisk.find('./target')
        xtarget.attrib['dev'] = 'sd' + ascii_lowercase[len(devs)]
        xtarget.tail = xtarget.tail[:-2]  # Remove one indent level.
        xdisk.remove(xdisk.find('./address'))
        # Try to place disk after first one.
        xdevices.insert(1 + len(devs), xdisk)

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


class LibVirtStoragePool(object):
    def __init__(self, pool):
        self.pool = pool

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.pool.name())

    def create_disk(self, name, size):
        try:
            disk = self.pool.storageVolLookupByName(name)
        except libvirt.libvirtError:
            pass
        else:
            logger.debug("Reusing disk %s.", name)
            return LibVirtDisk(disk)

        # For now, just clone definition of first disk found in pool.
        vol0 = self.pool.listAllVolumes()[0]
        xvol = ET.fromstring(vol0.XMLDesc())
        xvol.find('./name').text = name
        xkey = xvol.find('./key')
        xkey.text = os.path.dirname(xkey.text) + "/" + name
        xvol.find('./target/path').text = xkey.text
        xvol.find('./capacity').text = "%d" % size
        # Prallocate 256K, for partition, PV metadata and mkfs.
        xvol.find('./allocation').text = "%d" % (256 * 1024,)
        xvol.remove(xvol.find('./physical'))

        logger.debug("Creating disk %s.", name)
        handle = self.pool.createXML(ET.tostring(xvol, encoding='unicode'))
        return LibVirtDisk(handle)
