# Hacking cornac


## Variables

cornac tries to be very customizable while offering good defaults. Based on
[Ansible Variable
precedence](http://docs.ansible.com/ansible/latest/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable),
here is where to put variables in cornac.


- `group_vars/all.yml` (playbook group vars for all group) contains
  **defaults**.
- `inventory.d/group_vars/cornac.yml` (inventory group vars for cornac groups)
  contains **customized** variables.

This way, customized variables overrides defaults. Defaults should be accessible
through `…_defaults` variables:

``` yaml
cornac_sysctl_defaults:
  vm.overcommit_memory: 0
cornac_sysctl: '{{ cornac_sysctl_defaults }}'
```

This way, custom `cornac.yml` can references `cornac_sysctl_defaults` as well as
totally override `cornac_sysctl`.

cornac must never provide `group_vars/cornac.yml` since it will override
inventory vars.


## Release

`make build` creates an Ansible project with cornac's playbook and custom
inventory as defined in `ANSIBLE_INVENTORY` in `BUILDDIR`.

``` console
$ make build ANSIBLE_INVENTORY=$custom
...
$ cd build/
$ ansible-playbook install.yml
```
