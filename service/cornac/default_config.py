#
#       D E F A U L T   C O N F I G U R A T I O N
#

import os


# DSN to Postgres database.
DATABASE = os.environ.get('CORNAC_DATABASE')

# Domain suffix to resolve guest IP from DNS.
DNS_DOMAIN = ''

# IAAS URL, starting with provider prefix, + sign and provider specific URL.
# e.g. libvirt, vcenter+https://me:password@vcenter.acmi.lan/?no_verify=1
IAAS = None

# Provider specific guest network.
#
# For vSphere, use absolute path e.g. 'datacenter1/network/Guest Network'
NETWORK = None

# Provider specific name of the template machine to clone. You must install
# Postgres and other tools. See appliance/ for how to maintain this template
# with Ansible.
#
# For vSphere, must be a full path to the VM. e.g.
# datacenter1/vm/templates/base-cornac.
ORIGINAL_MACHINE = 'base-cornac'

# Provider-specific name of the storage pool (or datastore in vSphere).
STORAGE_POOL = 'default'

# SSH Public key used for deployement and maintainance of guests.
ROOT_PUBLIC_KEY = None

# vCenter specific resource pool where to place guests. Could be a host or a
# cluster resource pool. e.g. 'datacenter1/host/esxi1/Resources
VCENTER_RESOURCE_POOL = None
