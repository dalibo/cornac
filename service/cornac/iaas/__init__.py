#
# IaaS object manages machine, disk and networking.
#


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
        modname, clsname = cls.registry[name].split(':')
        mod = __import__(modname, fromlist=[clsname], level=0)
        return getattr(mod, clsname)

    @classmethod
    def connect(cls, url, config):
        provider, _, url = url.partition('+')
        iaas_cls = cls.load_iaas(provider)
        # Let's provider class analyze URL.
        return iaas_cls.connect(url, config)

    # By inheriting this class, IaaS provider implementation gains context
    # management to properly close resources.
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        pass
