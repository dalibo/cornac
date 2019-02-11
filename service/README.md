# REST Service

The Cornac webservice is an open-source implementation of AWS RDS API enabling
the use of aws CLI to manage your Postgres instances.


## Features

- RDS-like API compatible with awscli.
- Configurable infastructure provider: libvirt, VMWare.


## Prerequisites

Cornac webservice has the following prerequisites:

- SSH agent up and running with a private key.
- VM must be accessible through SSH. The following documentation use `.virt` as
  resolvable domain for virtual machines.
- a template VM called `base-cornac` with Postgres 11.

Further prerequisites depends on the infrastructure provider.


### libvirt Prerequisites

To use libvirt operator, install cornac with `libvirt` extra:

``` console
$ pip install -e .[libvirt]
```

libvirt operator has the following prerequisites.

- libvirt-daemon, virtinst and libguestfs-tools installed.
- libvirt unattended access.


### VMWare Prerequisites

To use VMWare operator, install cornac with `vmware` extra:

``` console
$ pip install -e .[vmware]
```

You must now configure `IAAS` parameter with the form:
`vcenter+https://user@sso.local:password@host/?no_verify=1`.


## Building the Template VM

- Create a CentOS7 VM, usually named `base-cornac`.
- For VMWare, inject the SSH public key for root user.
- Use `install.yml` playbook from `appliance/` directory to provision the VM. On
  vSphere, add the `vmware` feature.

``` console
$ cd appliance/
$ ansible-playbook install.yml -e host=base-cornac.virt -e features=vmware
$ ssh root@base-cornac.virt test -x /usr/pgsql-11/bin/initdb
```

Once the template is ready, shut it down and continue using cornac and aws CLI.


## Using awscli

First, run the webservice in a terminal:

``` console
$ CORNAC_SETTINGS=poc.cfg FLASK_APP=cornac.web flask run
```

Then, setup AWSCLI profile:

``` console
$ pip install awscli awscli-plugin-endpoint
$ aws configure set plugins.endpoint awscli_plugin_endpoint
$ aws configure --profile local  # Use dumb values.
$ aws configure --profile local set rds.endpoint_url http://localhost:5000  # Point to flask address
```

Now use `aws` as usual:

``` console
$ AWS_PROFILE=local aws rds create-db-instance --db-instance-identifier test0 --db-instance-class db.t2.micro --engine postgres --allocated-storage 5 --master-username postgres --master-user-password C0nfidentiel
$ AWS_PROFILE=local aws rds describe-db-instances  # Wait for state to be running
$ psql -h <endpoint-address> -p 5432 -U postgres -d test0
…: <type Master User Password>
```
