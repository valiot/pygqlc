#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

# reference: https://stackoverflow.com/questions/458550/standard-way-to-embed-version-into-python-package#:~:text=should%20be%20placed%20after%20the,previous%20version%20of%20this%20standard).&text=It%20should%20be%20a%20string,version_info%20for%20the%20tuple%20version.
def get_package_version(version_file):
    import re
    verstrline = open(version_file, "rt").read()
    VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
    mo = re.search(VSRE, verstrline, re.M)
    if mo:
        verstr = mo.group(1)
        return verstr
    else:
        raise RuntimeError("Unable to find version string in %s." % (version_file,))

__version__ = get_package_version("pygqlc/__version__.py")

requirements = [
    # TODO: put package requirements here
    'requests==2.26.0',
    'python-dotenv',
    'pydash==5.0.2',
    'websocket-client==0.54.0',
    'tenacity==6.3.1',
]

setup_requirements = [
    # TODO(alanbato): put setup requirements (distutils extensions, etc.) here
]

test_requirements = [
    # TODO: put package test requirements here
    'pytest',
]

desc = "GraphQL API Client for python language"
with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='pygqlc',
    version=__version__,
    description=desc,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Valiot",
    author_email='hiring@valiot.io',
    url='https://github.com/valiot/pygqlc',
    packages=find_packages(include=['pygqlc']),
    entry_points={
        'console_scripts': [
            'pygqlc=pygqlc.__main__:main'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    zip_safe=False,
    keywords='pygqlc',
    test_suite='tests',
    tests_require=test_requirements,
    setup_requires=setup_requirements,
)
