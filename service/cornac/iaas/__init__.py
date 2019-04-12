#
# IaaS object manages machine, disk and networking.
#

import logging

from ..errors import KnownError


logger = logging.getLogger(__name__)


class IaaS(object):
    registry = {
        # IaaS loads provider class lazily to avoid importing irrelevant
        # third-party library. The module path has the same format of
        # setuptools entrypoint.
        'libvirt': __name__ + '.libvirt:LibVirtIaaS',
        'vcenter': __name__ + '.vcenter:vCenter',
    }

    @classmethod
    def load_iaas(cls, name):
        try:
            modname, clsname = cls.registry[name].split(':')
        except KeyError:
            raise KnownError(f"Unknown IaaS type {name}.")
        mod = __import__(modname, fromlist=[clsname], level=0)
        return getattr(mod, clsname)

    @classmethod
    def connect(cls, url, config):
        provider, _, url = url.partition('+')
        iaas_cls = cls.load_iaas(provider)
        # Let's provider class analyze URL.
        try:
            return iaas_cls.connect(url, config)
        except Exception as e:
            msg = f"Failed to connect to {provider} at '{url}': {e}"
            raise KnownError(msg)

    @property
    def origin(self):
        return self.config['MACHINE_ORIGIN'].format(**self.config)

    @property
    def prefix(self):
        return self.config['MACHINE_PREFIX']

    # By inheriting this class, IaaS provider implementation gains context
    # management to properly close resources.
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        pass

    def machine_name(self, name):
        return self.prefix + name
