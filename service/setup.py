from setuptools import setup

setup(
    name='cornac',
    version='0.0.1',
    install_requires=[
        # Flask already depends on click, but we use it directly too.
        "click",
        "flask",
        "tenacity",
    ],
    extras_require={
        'libvirt': ["libvirt-python"],
        'vmware': ["pyvmomi"],
    },
    entry_points={
        'console_scripts': ['cornac = cornac.cli:entrypoint'],
    }
)
