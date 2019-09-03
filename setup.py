#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages
from pygqlc import __version__

requirements = [
    # TODO: put package requirements here
    'requests',
    'python-dotenv',
    'pydash',
    'python-dotenv',
    'websocket-client==0.54.0',
    'singleton-decorator',
    'tenacity',
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
    author="Baruc Almaguer",
    author_email='baruc@valiot.io',
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
