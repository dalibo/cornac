# Postgres VM provisionning


cornac provide a generic Ansible playbook to deploy Postgres on a YUM-based
distribution.

Cornac requirement is Ansible.


## Targeting Deployment

By default, cornac does not require any host in inventory. It fallbacks to
`localhost`. You can specify a target host with either `-e host=myhost` or
`CORNAC_HOST=myhost`. This implement one time deployment.

``` console
$ ansible-playbook install.yml -e host=myhost
...
PLAY RECAP *****************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0
myhost                     : ok=8    changed=0    unreachable=0    failed=0

$ CORNAC_HOST=myhost ansible-playbook install.yml
...
PLAY RECAP *****************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0
myhost                     : ok=8    changed=0    unreachable=0    failed=0

$
```

When adding several hosts in an inventory file, ensure they are members of
`cornac` host group. cornac playbooks acts only on `cornac` host group.

``` console
$ cat inventory.d/my-hosts.ini
[cornac]
myhost0
myhost1
$ ansible-playbook install.yml -l myhost0
...
PLAY RECAP *****************************************************************
myhost0                    : ok=8    changed=0    unreachable=0    failed=0

$
```


## Sharing SSH key between hosts

For Replication and High-Availibility cluster, you may want to share SSH key
between hosts. `sshkeys.yml` takes care of creating and sharing public user key
and host key between hosts.

If you have several HA cluster or just want to limit SSH key sharing for a
subset of your inventory, create a host subgroup of cornac host group. Then use
`--limit` option of *Ansible* to share SSH key only inside this group.


``` console
$ cat inventory.d/my-hosts.ini
[prod]
prod0
prod1

[cornac]
preprod

[cornac:children]
prod
$ ansible-playbook sshkeys.yml --limit socle10
...
PLAY RECAP *********************************************************************
prod0             : ok=9    changed=0    unreachable=0    failed=0
prod1             : ok=9    changed=0    unreachable=0    failed=0

```
