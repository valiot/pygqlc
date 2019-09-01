#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages
from pygqlc.version import version as version

requirements = [
    # TODO: put package requirements here
    'requests',
    'python-dotenv',
    'pydash',
    'python-dotenv',
]

setup_requirements = [
    # TODO(alanbato): put setup requirements (distutils extensions, etc.) here
]

test_requirements = [
    # TODO: put package test requirements here
    'pytest',
]

desc = "GraphQL API Client for python language"
setup(
    name='pygqlc',
    version=version,
    description=desc,
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
