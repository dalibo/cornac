# REST Service

The Cornac webservice is an open-source implementation of AWS RDS API enabling
the use of aws CLI to manage your Postgres instances.

**⚠ This project is at its early stage of development. ⚠**


## Features

- Subset of RDS API compatible with awscli.
- Configurable infastructure provider: libvirt, VMWare.


## Prerequisites

Cornac webservice has the following prerequisites:

- `python3.6-dev` and `libev-dev` on Debian or `python36-devel` and
  `libev-devel` from EPEL.
- SSH agent up and running with a private key.
- VM must be accessible through SSH. The following documentation use `.virt` as
  resolvable domain for virtual machines.

By default, cornac reads `config.py` in working directory if it exists.
`config.py` is a python file containing regular
[Flask configuration](http://flask.pocoo.org/docs/1.0/config/#configuring-from-files)
and cornac configuration. [Default cornac
configuration](cornac/core/config/defaults.py) is a good starting point to write
your own.

Further prerequisites depends on the infrastructure provider.


### libvirt Prerequisites

To use libvirt infrastructure, install cornac with `libvirt` extra:

``` console
$ pip install .[psycopg2-binary,libvirt]
```

libvirt infrastructure has the following prerequisites.

- libvirt-daemon, virtinst and libguestfs-tools installed.
- libvirt unattended access.


### VMWare Prerequisites

To use VMWare infrastructure, install cornac with `vmware` extra:

``` console
$ pip install .[psycopg2-binary,vmware]
```

You must now configure `IAAS` parameter with the form like:

``` python
IAAS = "vcenter+https://user@sso.local:password@host/?no_verify=1"
```


## Building the Template VM

Cornac webservice clone a template to provision a new Postgres host. You must
prepare this VM before calling cornac API.

- Create a CentOS7 VM, usually named `cornac--origin`.
- Inject the SSH public key for root user.
- Use `install.yml` playbook from `appliance/` directory to provision the VM. On
  vSphere, add the `vmware` feature.

``` console
$ cd appliance/
$ ansible-playbook install.yml -e host=cornac--origin.virt -e features=vmware
$ ssh root@base-cornac.virt test -x /usr/pgsql-11/bin/initdb
```

Once the template is ready, shut it down. On VMWare, create a snapshot. Then
continue using cornac and aws CLI.


## Setup Cornac Webservice

Cornac requires a Postgres database to maintain it's inventory. Fortunately,
cornac is able to self-bootstrap this Postgres instance using it's CLI.

The bootstrap command creates the instance and role according to the connection
URI. Set [Postgres connection
URI](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
in `SQLALCHEMY_DATABASE_URI` option in config file and run bootstrap like this:

```
$ cornac bootstrap
```

Great! You already have one managed Postgres instance! Two distinct services
runs cornac: the webserver and the background worker. Run each of them in a
separate terminal.

For the background worker:

``` console
$ cornac worker --processes 1
```

The web service requires credentials. You can generate a credentials pair with
`cornac` CLI:

``` console
$ cornac generate-credentials --save
```

The `--save` flags trigger configuration update. See logs for details. Keep
access key and secret key pair near to configure awscli later. Now run cornac
webservice with:

``` console
$ cornac run
```

Cornac is now ready to accept authenticated RDS requests!


## Using awscli

Finally, setup AWSCLI profile. Default cornac's region is `local`. To use cornac
as an alternative endpoint, awscli requires the endpoint plugin. This consists
of the following commands:

``` console
$ pip install awscli awscli-plugin-endpoint
$ aws configure set plugins.endpoint awscli_plugin_endpoint
$ aws configure --profile local
AWS Access Key ID: <the access key>
AWS Secret Access Key: <the secret key>
Default region name: local
…
$ aws configure --profile local set rds.endpoint_url http://localhost:5000/rds  # Point to cornac listen URL
```

Now use `aws` as usual:

``` console
$ AWS_PROFILE=local aws rds create-db-instance --db-instance-identifier test0 --db-instance-class db.t2.micro --engine postgres --allocated-storage 5 --master-username postgres --master-user-password C0nfidentiel
$ AWS_PROFILE=local aws rds describe-db-instances  # Wait for state to be running
$ psql -h <endpoint-address> -p 5432 -U postgres -d test0
…: <type Master User Password>
```
