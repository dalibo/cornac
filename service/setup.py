from setuptools import setup

setup(
    name='cornac',
    version='0.0.1',
    install_requires=[
        "flask",
        "tenacity",
    ],
    extras_require={
        'libvirt': ["libvirt-python"],
        'vmware': ["pyvmomi"],
    },
)
