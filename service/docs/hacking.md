# Hacking on cornac

Cornac webservice is a Python3 project based on Flask framework. The project is
managed with [poetry](https://poetry.eustace.io/).


## Prerequisites

Cornac webservice has the following prerequisites:

- On Debian: `libev-dev libvirt-dev python3.6-dev`.
- On CentOS: `libev-devel libvirt-devel python36-devel` from EPEL.
- SSH agent up and running with a private key loaded.
- VM must be accessible through SSH. The following documentation uses `.virt` as
  resolvable domain for virtual machines.

``` console
$ poetry install -E psycopg2-binary -E libvirt -E vmware
```

Further prerequisites depends on the infrastructure provider.


### libvirt Prerequisites

libvirt infrastructure has the following prerequisites.

- libvirt-daemon, virtinst and libguestfs-tools installed.
- libvirt unattended access.


### VMWare Prerequisites

You must configure `IAAS` parameter with the form like:

``` python
IAAS = "vcenter+https://user@sso.local:password@host/?no_verify=1"
```

Alternatively, you can define `CORNAC_IAAS` environment variable.


## Running

Create cornac owns instance with `cornac bootstrap`.

Run background worker with `cornac --verbose worker -p 1 -t 2`.

Run dev server with `cornac --verbose run`. Follow [installation
instructions](install.md) for awscli setup.

Run unit tests with `pytest tests/unit/` and func tests with `pytest
tests/func/`.
