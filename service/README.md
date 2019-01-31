# REST Service

The Cornac REST service is an open-source implémentation of AWS RDS API enabling
the use of aws CLI tool to manage your Postgres instances.


Prerequisites:

- libvirt-daemon, virtinst and libguestfs-tools.
- Resolution of VM with domain `.virt`.
- SSH agent up and running.
- libvirt unattended access.
- a VM called `base-cornac` with Postgres 11.


Quick setup:

``` console
$ pip install -e .
$ FLASK_APP=cornac.web flask run
```


Setup AWSCLI profile:

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
