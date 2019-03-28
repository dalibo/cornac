#
# IaaS provider on top of vSphere API
#
# cf. https://code.vmware.com/apis/358/vsphere
#

import logging
from contextlib import contextmanager
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
from ..errors import (
    KnownError,
    RemoteCommandError,
)
from ..ssh import RemoteShell


logger = logging.getLogger(__name__)


@contextmanager
def lint_error():
    # pyVmomi errors string serialization is ugly. This context manager reraise
    # errors with clean message.
    try:
        yield None
    except vmodl.MethodFault as e:
        raise Exception(e.msg) from e


class vCenter(IaaS):
    @classmethod
    def connect(cls, url, config):
        url = urlparse(url)
        args = parse_qs(url.query)
        no_verify = args.get('no_verify', ['0']) == ['1']
        connector = SmartConnectNoSSL if no_verify else SmartConnect
        with lint_error():
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
        name = f"cornac-{name}"
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

        if len(origin.rootSnapshot):
            sstree = origin.snapshot.rootSnapshotList[0]
            logger.debug("Using linked clone from '%s'.", sstree.name)
            clonespec.snapshot = sstree.snapshot
            locspec.diskMoveType = 'createNewChildDiskBacking'

        logger.debug("Cloning %s as %s.", origin.name, name)
        task = origin.Clone(folder=origin.parent, name=name, spec=clonespec)
        try:
            machine = self.wait_task(task)
        except vim.fault.DuplicateName:
            raise KnownError(f"VM {name} already exists.")

        self.sysprep(machine)
        return machine

    def delete_machine(self, machine):
        machine = self._ensure_machine(machine)
        if 'poweredOn' == machine.runtime.powerState:
            logger.debug("Powering off %s.", machine)
            with self.wait_update(machine, 'runtime.powerState'):
                self.wait_task(machine.PowerOff())
        logger.debug("Destroying %s.", machine)
        return self.wait_task(machine.Destroy_Task())

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

    def list_machines(self):
        for child in self.si.content.rootFolder.childEntity:
            if not hasattr(child, 'vmFolder'):
                continue

            for machine in child.vmFolder.childEntity:
                if machine.name.startswith('cornac-'):
                    yield machine

    def _ensure_machine(self, machine_or_name):
        if isinstance(machine_or_name, str):
            vmfolder = Path(self.config['ORIGINAL_MACHINE']).parent
            machine_or_name = self.find(f"{vmfolder}/cornac-{machine_or_name}")
        return machine_or_name

    def _ensure_tools(self, machine):
        machine = self._ensure_machine(machine)
        if 'toolsOk' == machine.guest.toolsStatus:
            return

        with self.wait_update(machine, 'guest.toolsStatus'):
            logger.debug("Wait for tools to come up on %s.", machine)

        if 'toolsOk' != machine.guest.toolsStatus:
            msg = f"{machine} tools at state {machine.guest.toolsStatus}."
            raise KnownError(msg)

    def start_machine(self, machine, wait_ssh=False, wait_tools=False):
        machine = self._ensure_machine(machine)
        if 'poweredOn' == machine.runtime.powerState:
            logger.debug("%s is already powered.", machine)
        else:
            with self.wait_update(machine, 'runtime.powerState'):
                logger.debug("Powering %s on.", machine)
                self.wait_task(machine.PowerOn())

        if wait_ssh:
            ssh = RemoteShell('root', self.endpoint(machine))
            ssh.wait()

        if wait_tools:
            self._ensure_tools(machine)

    def stop_machine(self, machine):
        machine = self._ensure_machine(machine)
        if 'poweredOff' == machine.runtime.powerState:
            return logger.debug("Already stopped.")

        with self.wait_update(machine, 'runtime.powerState'):
            shut = False
            if 'toolsOk' != machine.guest.toolsStatus:
                # If tools are slow to come up, try SSH before waiting for
                # tools. That may be faster.
                ssh = RemoteShell('root', self.endpoint(machine))
                logger.debug("Shuting down %s through SSH.", machine)
                try:
                    ssh(["shutdown", "-h", "now"])
                except RemoteCommandError as e:
                    if e.connection_closed_by_remote:
                        # Connection closed, it's fine, let's wait powerOff.
                        shut = True
                    else:
                        logger.debug("SSH shutdown failed: %s.", e)

            if not shut:
                logger.debug("Shuting down %s through vTools.", machine)
                self._ensure_tools(machine)
                machine.ShutdownGuest()

    def sysprep(self, machine):
        endpoint = self.endpoint(machine)
        logger.debug("Waiting for %s to come up.", endpoint)
        ssh = RemoteShell('root', endpoint)
        ssh.wait()
        vhelper = str(Path(__file__).parent / 'vhelper.sh')
        ssh.copy(vhelper, "/usr/local/bin/vhelper.sh")
        logger.debug("Preparing system")
        ssh(["/usr/local/bin/vhelper.sh", "sysprep"])

    @contextmanager
    def wait_update(self, obj, proppath):
        propSpec = vmodl.query.PropertyCollector.PropertySpec(
            type=type(obj), all=False, pathSet=[proppath])
        filterSpec = vmodl.query.PropertyCollector.FilterSpec(
            objectSet=[vmodl.query.PropertyCollector.ObjectSpec(obj=obj)],
            propSet=[propSpec],
        )

        pc = self.si.content.propertyCollector
        waitopts = vmodl.query.PropertyCollector.WaitOptions(
            maxWaitSeconds=300)
        pcFilter = pc.CreateFilter(filterSpec, partialUpdates=True)
        try:
            initset = pc.WaitForUpdatesEx(version='', options=waitopts)
            yield
            logger.debug("Waiting for update on %s.%s.", obj, proppath)
            return pc.WaitForUpdatesEx(initset.version, options=waitopts)
        finally:
            pcFilter.Destroy()

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
