# Implementation of IaaS based on libvirt tools.
#
# Uses libvirt binding, virt-manager and guestfs tools to manage VM.
# Current purpose is PoC or development.


import logging
import os
from copy import deepcopy
from string import ascii_lowercase
from xml.etree import ElementTree as ET
from time import sleep

import libvirt

from . import IaaS
from ..errors import Timeout
from ..ssh import logged_cmd


logger = logging.getLogger(__name__)


_1G = 1024 * 1024 * 1024


class LibVirtIaaS(IaaS):
    @classmethod
    def connect(cls, url, config):
        return cls(libvirt.open(), config)

    def __init__(self, conn, config):
        self.conn = conn
        self.config = config
        # Configuration Keys:
        #
        # DEPLOY_KEY: SSH public key to inject to access root account
        #                  on new machines.
        # DNS_DOMAIN: DNS domain to build FQDN of machine on the IaaS.

    def attach_disk(self, domain, disk):
        xml = domain.XMLDesc()
        path = disk.path()
        disk.machine = self
        if path in xml:
            logger.debug("Disk %s already attached to %s.", path, disk.name())
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
        self.conn.defineXML(xml)

    def close(self):
        self.conn.close()

    def create_disk(self, pool, name, size_gb):
        name = f"{name}.qcow2"
        pool = self.conn.storagePoolLookupByName(pool)
        try:
            disk = pool.storageVolLookupByName(name)
        except libvirt.libvirtError:
            pass
        else:
            logger.debug("Reusing disk %s.", name)
            return disk

        # For now, just clone definition of first disk found in pool.
        vol0 = pool.listAllVolumes()[0]
        xvol = ET.fromstring(vol0.XMLDesc())
        xvol.find('./name').text = name
        xvol.find('./capacity').text = "%d" % (size_gb * _1G)
        # Prallocate 256K, for partition, PV metadata and mkfs.
        xvol.find('./allocation').text = "%d" % (256 * 1024,)

        xvol.remove(xvol.find('./key'))
        xvol.remove(xvol.find('./physical'))
        xtarget = xvol.find('./target')
        xtarget.remove(xtarget.find('./path'))

        logger.debug("Creating disk %s.", name)
        return pool.createXML(ET.tostring(xvol, encoding='unicode'))

    def create_machine(self, name, storage_pool, data_size_gb, **kw):
        name = f"{self.prefix}{name}"
        # The PoC reuses ressources until we have persistence of objects.
        try:
            domain = self.conn.lookupByName(name)
        except libvirt.libvirtError:
            clone_cmd = [
                "virt-clone",
                "--original", self.origin,
                "--name", name,
                "--auto-clone",
            ]
            logger.debug("Allocating machine %s.", name)
            logged_cmd(clone_cmd)
            domain = self.conn.lookupByName(name)
        else:
            logger.debug("Reusing VM %s.", name)

        state, _ = domain.state()
        if libvirt.VIR_DOMAIN_SHUTOFF == state:
            prepare_cmd = [
                "virt-sysprep",
                "--domain", name,
                "--hostname", name,
                "--selinux-relabel",
            ]
            if self.config['DEPLOY_KEY']:
                prepare_cmd.extend([
                    "--ssh-inject",
                    f"root:string:{self.config['DEPLOY_KEY']}",
                ])
            logger.debug("Preparing machine %s.", name)
            logged_cmd(prepare_cmd)

        disk = self.create_disk(storage_pool, f'{name}-data', data_size_gb)
        self.attach_disk(domain, disk)

        return domain

    def delete_machine(self, domain):
        try:
            domain = self._ensure_domain(domain)
        except libvirt.libvirtError as e:
            if 'Domain not found' in str(e):
                return logger.debug("Already deleted.")
            raise
        state, _ = domain.state()
        if self.is_running(domain):
            domain.destroy()

        xml = ET.fromstring(domain.XMLDesc())
        for xsource in xml.findall('./devices/disk/source'):
            file_ = xsource.attrib['file']
            logger.debug("Deleting disk image %s.", file_)
            os.unlink(file_)

        logger.debug("Undefining domain %s.", domain.name())
        domain.undefineFlags(
            libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
            libvirt.VIR_DOMAIN_UNDEFINE_NVRAM |
            libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA |
            0
        )

    def is_running(self, domain_or_name):
        domain = self._ensure_domain(domain_or_name)
        state, _ = domain.state()
        return libvirt.VIR_DOMAIN_RUNNING == state

    def list_machines(self):
        for domain in self.conn.listAllDomains():
            name = domain.name()
            if name == self.origin:
                continue
            if name.startswith(self.prefix):
                yield domain

    def _ensure_domain(self, domain_or_name):
        if isinstance(domain_or_name, str):
            name = f"{self.prefix}{domain_or_name}"
            domain_or_name = self.conn.lookupByName(name)
        return domain_or_name

    def endpoint(self, domain_or_name):
        domain = self._ensure_domain(domain_or_name)
        # Let's DNS resolve machine IP for now.
        return domain.name() + self.config['DNS_DOMAIN']

    def guess_data_device_in_guest(self, machine):
        # Guess /dev/disk/by-path/… device file from XML.
        xml = ET.fromstring(machine.XMLDesc())
        name = f'{machine.name()}-data'
        for xdisk in xml.findall(".//disk"):
            if name in xdisk.find('./source').attrib['file']:
                xdiskaddress = xdisk.find('./address')
                break
        else:
            raise Exception(f"Can't find disk {name} in VM.")

        xcontrolleraddress = xml.find(
            ".//controller[@type='scsi']/address[@type='pci']")
        pci_path = 'pci-{domain:04x}:{bus:02x}:{slot:02x}.{function}'.format(
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

    def start_machine(self, domain, wait=300):
        domain = self._ensure_domain(domain)
        name = domain.name()
        state, _ = domain.state()
        if self.is_running(domain):
            logger.debug("VM %s running.", name)
        else:
            logger.info("Starting VM %s.", name)
            domain.create()
        self.wait_state(domain, libvirt.VIR_DOMAIN_RUNNING, wait)

    def stop_machine(self, domain, wait=60):
        domain = self._ensure_domain(domain)
        name = domain.name()
        state, _ = domain.state()
        if libvirt.VIR_DOMAIN_SHUTOFF == state:
            logger.debug("VM %s stopped.", name)
        else:
            logger.info("Stopping VM %s.", name)
            domain.shutdown()

        self.wait_state(domain, libvirt.VIR_DOMAIN_SHUTOFF, wait)

    def wait_state(self, domain, wanted, wait=60):
        if not wait:
            return

        for _ in range(int(wait)):
            state, _ = domain.state()
            if wanted == state:
                break
            else:
                sleep(1)
            wait -= 1
        else:
            raise Timeout()
