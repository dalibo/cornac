# REST Service

The Cornac webservice is an open-source implementation of AWS RDS API enabling
the use of aws CLI to manage your Postgres instances.

**⚠ This project is at its early stage of development. ⚠**


## Features

- Subset of RDS API compatible with awscli.
- Configurable infastructure provider: libvirt, VMWare.


## Prerequisites

Cornac webservice has the following prerequisites:

- SSH agent up and running with a private key.
- VM must be accessible through SSH. The following documentation use `.virt` as
  resolvable domain for virtual machines.
- a template VM called `base-cornac` with Postgres 11.

The `CORNAC_SETTINGS` environment variable point to a python file containing
regular Flask configuration and cornac configuration. [Default cornac
configuration](cornac/default_config.py) is commented. A [poc.cfg](poc.cfg)
configuration file can be a good starting point.

Further prerequisites depends on the infrastructure provider.


### libvirt Prerequisites

To use libvirt infrastructure, install cornac with `libvirt` extra:

``` console
$ pip install -e .[psycopg2-binary,libvirt]
```

libvirt infrastructure has the following prerequisites.

- libvirt-daemon, virtinst and libguestfs-tools installed.
- libvirt unattended access.


### VMWare Prerequisites

To use VMWare infrastructure, install cornac with `vmware` extra:

``` console
$ pip install -e .[psycopg2-binary,vmware]
```

You must now configure `IAAS` parameter with the form like:

``` python
IAAS = "vcenter+https://user@sso.local:password@host/?no_verify=1"
```


## Building the Template VM

Cornac webservice clone a template to provision a new Postgres host. You must
prepare this VM before calling cornac API.

- Create a CentOS7 VM, usually named `base-cornac`.
- Inject the SSH public key for root user.
- Use `install.yml` playbook from `appliance/` directory to provision the VM. On
  vSphere, add the `vmware` feature.

``` console
$ cd appliance/
$ ansible-playbook install.yml -e host=base-cornac.virt -e features=vmware
$ ssh root@base-cornac.virt test -x /usr/pgsql-11/bin/initdb
```

Once the template is ready, shut it down and continue using cornac and aws CLI.


## Setup Cornac Webservice

Cornac requires a Postgres database to maintain it's inventory. Fortunately,
cornac is able to self-bootstrap this Postgres instance using it's CLI.

The Bootstrap command creates the instance and user according to the connection
URI. Set [Postgres connection
URI](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
in `DATABASE` option in config file and run bootstrap like this:

```
$ cornac bootstrap
```

Great! You already have one managed Postgres instance! Now run the webservice in
a terminal:

``` console
$ CORNAC_SETTINGS=poc.cfg FLASK_APP=cornac.web flask run
```

Cornac is now ready to accept any RDS request!


## Using awscli

Finally, setup AWSCLI profile:

``` console
$ pip install awscli awscli-plugin-endpoint
$ aws configure set plugins.endpoint awscli_plugin_endpoint
$ aws configure --profile local  # Use dumb values.
$ aws configure --profile local set rds.endpoint_url http://localhost:5000/rds  # Point to flask address
```

Now use `aws` as usual:

``` console
$ AWS_PROFILE=local aws rds create-db-instance --db-instance-identifier test0 --db-instance-class db.t2.micro --engine postgres --allocated-storage 5 --master-username postgres --master-user-password C0nfidentiel
$ AWS_PROFILE=local aws rds describe-db-instances  # Wait for state to be running
$ psql -h <endpoint-address> -p 5432 -U postgres -d test0
…: <type Master User Password>
```
