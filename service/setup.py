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
        # psycopg2 can be either wheel binary or source. But it's actually
        # required. Using extras mimick *or* dependency. See
        # https://trac.edgewall.org/ticket/12989 for an example in Trac.
        'psycopg2': ["psycopg2"],
        'psycopg2-binary': ["psycopg2"],
        'vmware': ["pyvmomi"],
    },
    entry_points={
        'console_scripts': ['cornac = cornac.cli:entrypoint'],
    }
)
