#
#       D E F A U L T   C O N F I G U R A T I O N
#
# You can override every settings using environment by prefixing setting with
# CORNAC_. e.g CORNAC_IAAS will configure IAAS setting.

# Path to config file. By default, config.py in current directory.
CONFIG = 'config.py'

# A mapping of access key and secret key. See cornac generate-credentials for
# more.
CREDENTIALS = {}

# Domain suffix to resolve guest IP from DNS.
DNS_DOMAIN = ''

# IAAS URL, starting with provider prefix, + sign and provider specific URL.
# e.g. libvirt, vcenter+https://me:password@vcenter.acmi.lan/?no_verify=1
IAAS = None

# Provider specific name of the template machine to clone. You must install
# Postgres and other tools. See appliance/ for how to maintain this template
# with Ansible.
#
# For vSphere, must be a full path to the VM. e.g.
# datacenter1/vm/templates/{MACHINE_PREFIX}-origin.
#
# The doubling of hyphen is wanted. It allow to avoid clashes with a db
# instance named origin.
MACHINE_ORIGIN = '{MACHINE_PREFIX}-origin'

# Prefix of VM in IaaS.
#
# This allow to isolate several instance of cornac in the same IaaS.
MACHINE_PREFIX = 'cornac-'

# Provider specific guest network.
#
# For vSphere, use absolute path e.g. 'datacenter1/network/Guest Network'
NETWORK = None

# Region name as used for request signing.
REGION = 'local'

# DSN to Postgres database.
SQLALCHEMY_DATABASE_URI = None

# Provider-specific name of the storage pool (or datastore in vSphere).
STORAGE_POOL = 'default'

# SSH Public key used for deployement and maintainance of guests.
DEPLOY_KEY = None

# vCenter specific resource pool where to place guests. Could be a host or a
# cluster resource pool. e.g. 'datacenter1/host/esxi1/Resources
VCENTER_RESOURCE_POOL = None


#
#       I N T E R N A L S
#
# Here cornac configures Flask and extensions. You should not overload this
# settings.

DRAMATIQ_BROKER = 'dramatiq_pg:PostgresBroker'
DRAMATIQ_BROKER_URL = None
SQLALCHEMY_TRACK_MODIFICATIONS = False
