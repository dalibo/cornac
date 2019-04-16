#
# IaaS provider on top of vSphere API
#
# cf. https://code.vmware.com/apis/358/vsphere
#

import logging
import os.path
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import (
    parse_qs,
    urlparse,
)

import tenacity
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


# Retryier for operation on vCenter when vCenter server loose connection to
# ESXi host.
retry_esx_connection = tenacity.retry(
    after=tenacity.after_log(logger, logging.DEBUG),
    reraise=True,
    retry=(tenacity.retry_if_exception_type(vim.fault.InvalidHostState) |
           tenacity.retry_if_exception_type(vmodl.fault.HostNotConnected)),
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_fixed(1),
)


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

    @retry_esx_connection
    def clone_machine(self, origin, name, clonespec):
        logger.debug("Cloning %s as %s.", origin.name, name)
        task = origin.Clone(folder=origin.parent, name=name, spec=clonespec)
        return self.wait_task(task)

    def close(self):
        logger.debug("Disconnecting from vSphere.")
        Disconnect(self.si)

    def create_machine(
            self, name, storage_pool, data_size_gb=None, **kw):
        name = f"{self.prefix}{name}"
        logger.debug("Creating %s specification.", name)
        datastore = self.find(storage_pool)
        origin = self.find(self.origin)

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

        try:
            machine = self.clone_machine(origin, name, clonespec)
        except vim.fault.DuplicateName:
            raise KnownError(f"VM {name} already exists.")

        self.sysprep(machine)
        return machine

    @retry_esx_connection
    def delete_machine(self, machine):
        machine = self._ensure_machine(machine)
        if 'poweredOn' == machine.runtime.powerState:
            logger.debug("Powering off %s.", machine)
            with self.wait_update(machine, 'runtime.powerState'):
                self.wait_task(machine.PowerOff())
        logger.debug("Destroying %s.", machine)
        return self.wait_task(machine.Destroy_Task())

    def endpoint(self, machine_or_name):
        machine = self._ensure_machine(machine_or_name)
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
        origin = os.path.basename(self.origin)
        for child in self.si.content.rootFolder.childEntity:
            if not hasattr(child, 'vmFolder'):
                continue

            for machine in child.vmFolder.childEntity:
                if origin == machine.name:
                    continue

                if machine.name.startswith(self.prefix):
                    yield machine

    def _ensure_machine(self, machine_or_name):
        if isinstance(machine_or_name, str):
            vmfolder = Path(self.origin).parent
            objpath = f"{vmfolder}/{self.prefix}{machine_or_name}"
            try:
                machine_or_name = self.find(objpath)
            except KeyError:
                raise KnownError(f"{objpath} does not exists in IaaS.")
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

    @retry_esx_connection
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

    @retry_esx_connection
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

    def iter_updates(self, obj, proppath, maxupdates=5):
        # Watch and yield first value and updates on one property of one
        # managed object.
        propSpec = vmodl.query.PropertyCollector.PropertySpec(
            type=type(obj), all=False, pathSet=[proppath])
        filterSpec = vmodl.query.PropertyCollector.FilterSpec(
            objectSet=[vmodl.query.PropertyCollector.ObjectSpec(obj=obj)],
            propSet=[propSpec])
        pc = self.si.content.propertyCollector
        waitopts = vmodl.query.PropertyCollector.WaitOptions(
            maxObjectUpdates=1, maxWaitSeconds=300)
        pcFilter = pc.CreateFilter(filterSpec, partialUpdates=True)

        try:
            update = pc.WaitForUpdatesEx('', options=waitopts)
            yield update.filterSet[0].objectSet[0]
            while maxupdates > 0:
                logger.debug("Waiting for update on %s.%s.", obj, proppath)
                update = pc.WaitForUpdatesEx(update.version, options=waitopts)
                yield update.filterSet[0].objectSet[0]
                maxupdates -= 1
        except GeneratorExit:
            pass
        finally:
            pcFilter.Destroy()

    @contextmanager
    def wait_update(self, obj, proppath):
        updates = self.iter_updates(obj, proppath)
        # First iteration generates current value.
        yield next(updates)
        # At exit, wait for next update before returning.
        next(updates)

    def wait_task(self, task):
        for update in self.iter_updates(task, 'info.state'):
            task = update.obj
            newstate = update.changeSet[0].val
            if newstate == vim.TaskInfo.State.success:
                return task.info.result
            elif newstate == vim.TaskInfo.State.error:
                raise task.info.error
            # Else, continue to wait.


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
