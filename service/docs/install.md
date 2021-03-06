# Installation

Installing Cornac web service consists of setting up the following compoments :

- A base VM called *origin*.
- An appliance with cornac web service and cornac background worker.
- awscli to consume the service.


## Prerequisites

Cornac webservice has the following prerequisites:

- CentOS 7 with EPEL.
- Packages `libev-devel libvirt-devel python36-devel python36-virtualenv`.
- Access to IaaS, either libvirt or vCenter.
- Resolvable DNS domain for VM. The following documentation use `.virt`.


## Installing

Get [install script](../packaging/install) and run it as root. This script
bundles cornac and it's dependencies in `/opt/cornac`.

Now run `/opt/cornac/bin/cornac-setup` to create users and directories in
`/etc/opt/cornac`. Cornac has two users: `cornac-web` and `cornac-worker`. The
latter is more privileged as it has access to IaaS and root access on Postgres
VM.


## Configuring

`cornac-setup` tries to make your life easier. However, you have several things
to configure yourself:

- Check Postgres connection URI generated by `cornac-setup`.
- Configure RDS credentials.
- Configure `IAAS` access and parameters.

There is two configuration files: `/etc/opt/cornac/web/cornac.py` and
`/etc/opt/cornac/worker/cornac.py`. The cornac-worker user reads both files.
However, cornac-web users can't access cornac-worker files.

`/etc/opt/cornac/web/cornac.py` defines `SQLALCHEMY_DATABASE_URI` for both web
and worker users. `cornac-setup` scripts generates one for you. Ensure it is a
meaningful [Postgres connection
URI](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
for your system.

Now, generate a new credentials pair to access the REST API. The
`generate-credentials` command helps you to generate this credentials. It
outputs a credentials file in CSV format as generated by AWS.
`generate-credentials` is able to append the credentials to
`/etc/opt/cornac/web/cornac.py` for you.

``` console
$ sudo -u cornac-web /opt/cornac/bin/cornac-shell cornac generate-credentials --save
…
$
```

Keep these credentials near. You'll need them to configure awscli later. Run it
each time to you want a new credentials. For now, every credentials has full
access to the API and instances.

Now edit `/etc/opt/cornac/worker/cornac.py` and set up `IAAS` configuration
option as well as vCenter options according to your infrastructure.


## Building the Origin VM

Cornac webservice clones an existing VM to provision a new Postgres host. You
must prepare this VM before calling cornac API.

- Create a CentOS7 VM, usually named `cornac--origin`.
- Inject the SSH public key ~cornac-worker/.ssh/id_rsa.pub for root user.
- Use `install.yml` playbook from `appliance/` directory to provision the VM. On
  vSphere, add the `vmware` feature.

``` console
$ cd appliance/
$ ansible-playbook install.yml -e host=cornac--origin.virt -e features=vmware
$ ssh root@base-cornac.virt test -x /usr/pgsql-11/bin/initdb
```

Once the template is ready, shut it down. On VMWare, create a snapshot.


## Bootstrapping

Cornac requires a Postgres database to maintain it's inventory. Fortunately,
cornac is able to self-bootstrap this Postgres instance using it's CLI.

The `/opt/cornac/bin/cornac-shell` scripts ensure a proper environment for
executing cornac commands: `PATH` is configured, SSH agent is up and loaded.
Enter cornac-worker workspace with `sudo -u cornac-worker
/opt/cornac/bin/cornac-shell`.

The bootstrap command creates the instance and role according to the Postgres
connection URI in `/opt/cornac/web/cornac.py`.

```
$ cornac bootstrap
```

On failure or misconfiguration, you can safely drop the VM and relaunch the
command. The `cornac` instance is your first managed Postgres instance!


## Running services

Two distinct services runs cornac: the webserver and the background worker. Each
have it's own unit file.

Begin with the background worker:

``` console
# systemctl enable cornac-worker
# systemctl start cornac-worker
```

Then the web service process:


``` console
# systemctl enable cornac-web
# systemctl start cornac-web
```

Cornac is now ready to accept authenticated RDS requests!


## Using awscli

Finally, setup AWSCLI profile. Default cornac's region is `local`. To use cornac
as an alternative endpoint, awscli requires the endpoint plugin. This consists
of the following commands:

``` console
$ pip install awscli awscli-plugin-endpoint
$ aws configure set plugins.endpoint awscli_plugin_endpoint
$ echo '[profile local]' >> ~/.aws/config
$ aws configure --profile local
AWS Access Key ID: <the access key>
AWS Secret Access Key: <the secret key>
Default region name: local
…
$ aws configure --profile local set rds.endpoint_url http://localhost:5000/rds  # Point to cornac listen URL
```

Now use `aws` as usual:

``` console
$ export AWS_PROFILE=local
$ aws rds create-db-instance --db-instance-identifier test0 --db-instance-class db.t2.micro --engine postgres --allocated-storage 5 --master-username postgres --master-user-password C0nfidentiel
$ aws rds describe-db-instances  # Wait for state to be running
$ psql -h <endpoint-address> -p 5432 -U postgres -d test0
…: <type Master User Password>
```
