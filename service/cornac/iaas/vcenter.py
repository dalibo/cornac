#
# IaaS provider on top of vSphere API
#
# cf. https://code.vmware.com/apis/358/vsphere
#

import logging
from pathlib import Path
from urllib.parse import (
    parse_qs,
    urlparse,
)


from pyVim.connect import (
    Disconnect,
    SmartConnect,
    SmartConnectNoSSL,
)
from pyVmomi import (
    vim,
    vmodl,
)

from . import IaaS
from ..ssh import RemoteShell


logger = logging.getLogger(__name__)


class vCenter(IaaS):
    @classmethod
    def connect(cls, url, config):
        url = urlparse(url)
        args = parse_qs(url.query)
        no_verify = args.get('no_verify', ['0']) == ['1']
        connector = SmartConnectNoSSL if no_verify else SmartConnect
        si = connector(
            host=url.hostname,
            user=url.username,
            pwd=url.password,
            port=url.port or 443,
        )
        return cls(si, config)

    def __init__(self, si, config):
        self.config = config
        # si stands for ServiceInstance.
        self.si = si

    def close(self):
        logger.debug("Disconnecting from vSphere.")
        Disconnect(self.si)

    def create_machine(
            self, name, storage_pool, data_size_gb=None, **kw):
        logger.debug("Creating %s specification.", name)
        datastore = self.find(storage_pool)
        origin = self.find(self.config['ORIGINAL_MACHINE'])

        clonespec = vim.vm.CloneSpec()
        clonespec.powerOn = True  # Let's power on the VM for sysprep.
        clonespec.config = vim.vm.ConfigSpec()
        clonespec.config.deviceChange.append(
            build_data_disk_spec(origin, datastore, name, data_size_gb)
        )
        clonespec.customization = build_customization_spec()
        clonespec.location = locspec = vim.vm.RelocateSpec()
        locspec.datastore = datastore
        locspec.pool = self.find(self.config['VCENTER_RESOURCE_POOL'])
        locspec.deviceChange.append(build_nic_spec(self.config['NETWORK']))

        logger.debug("Cloning %s as %s.", origin.name, name)
        task = origin.Clone(folder=origin.parent, name=name, spec=clonespec)
        machine = self.wait_task(task)
        self.sysprep(machine)
        return machine

    def endpoint(self, machine):
        return machine.name + self.config['DNS_DOMAIN']

    def find(self, path):
        obj = self.si.content.searchIndex.FindByInventoryPath(path)
        if obj is None:
            raise KeyError(path)
        return obj

    def guess_data_device_in_guest(self, machine):
        # It's quite hard to determine exact device inside linux guest from VM
        # spec. Let's assume things are simple and reproducible. cf.
        # https://communities.vmware.com/thread/298072
        return "/dev/sdb"

    def start(self, machine):
        return self.wait_task(machine.PowerOn())

    def stop(self, machine):
        return self.wait_task(machine.PowerOff())

    def sysprep(self, machine):
        endpoint = self.endpoint(machine)
        logger.debug("Waiting for %s to come up.", endpoint)
        ssh = RemoteShell('root', endpoint)
        ssh.wait()
        vhelper = str(Path(__file__).parent / 'vhelper.sh')
        ssh.copy(vhelper, "/usr/local/bin/vhelper.sh")
        logger.debug("Preparing system")
        ssh(["/usr/local/bin/vhelper.sh", "sysprep"])
        self.stop(machine)

    def wait_task(self, task):
        # From pyvmomi samples.
        collector = self.si.content.propertyCollector
        obj_specs = [vmodl.query.PropertyCollector.ObjectSpec(obj=task)]
        property_spec = vmodl.query.PropertyCollector.PropertySpec(
            type=vim.Task, pathSet=[], all=True)
        filter_spec = vmodl.query.PropertyCollector.FilterSpec()
        filter_spec.objectSet = obj_specs
        filter_spec.propSet = [property_spec]
        pcfilter = collector.CreateFilter(filter_spec, True)

        try:
            version = state = None
            while True:
                update = collector.WaitForUpdates(version)
                for filter_set in update.filterSet:
                    for obj_set in filter_set.objectSet:
                        task = obj_set.obj
                        for change in obj_set.changeSet:
                            if change.name == 'info':
                                state = change.val.state
                            elif change.name == 'info.state':
                                state = change.val
                            else:
                                continue

                            if state == vim.TaskInfo.State.success:
                                return task.info.result
                            elif state == vim.TaskInfo.State.error:
                                raise task.info.error
                version = update.version
        finally:
            pcfilter.Destroy()


def build_customization_spec():
    # To automatically set hostname, we need to create the minimal
    # customization spec which is no less than:
    spec = vim.vm.customization.Specification()
    spec.globalIPSettings = vim.vm.customization.GlobalIPSettings()
    nicsetting = vim.vm.customization.AdapterMapping()
    nicsetting.adapter = ipsettings = vim.vm.customization.IPSettings()
    ipsettings.ip = vim.vm.customization.DhcpIpGenerator()
    spec.nicSettingMap.append(nicsetting)
    spec.identity = ident = vim.vm.customization.LinuxPrep()
    ident.hwClockUTC = True
    ident.timeZone = 'Europe/Paris'
    # … here you are, we can tell vCenter to set hostname according to VM
    # name. \o/
    ident.hostName = vim.vm.customization.VirtualMachineNameGenerator()
    return spec


def build_data_disk_spec(origin, datastore, name, size_gb):
    spec = vim.vm.device.VirtualDeviceSpec()
    spec.fileOperation = 'create'
    spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    spec.device = disk = vim.vm.device.VirtualDisk()
    disk.capacityInKB = size_gb * 1024 * 1024
    scsi_controllers = list(filter(
        lambda d: hasattr(d, 'scsiCtlrUnitNumber'),
        origin.config.hardware.device
    ))
    disk.controllerKey = scsi_controllers[0].key
    disk.unitNumber = 1
    disks = list(filter(
        lambda d: hasattr(d.backing, 'diskMode'),
        origin.config.hardware.device
    ))
    disk.key = disks[-1].key + 1
    disk.unitNumber = disks[-1].unitNumber + 1
    disk.backing = backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()  # noqa
    backing.fileName = f'[{datastore.name}] {name}/{name}-data.vmdk'
    backing.thinProvisioned = False
    backing.diskMode = 'persistent'
    return spec


def build_nic_spec(network):
    spec = vim.vm.device.VirtualDeviceSpec()
    spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    spec.device = nic = vim.vm.device.VirtualVmxnet3()
    nic.addressType = 'assigned'
    nic.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
    nic.backing.useAutoDetect = False
    nic.backing.deviceName = network
    nic.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nic.connectable.startConnected = True
    return spec
