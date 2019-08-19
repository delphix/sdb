#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name='sdb',
    version="0.1.0",

    packages=[
        "sdb",
        "sdb.commands",
        "sdb.commands.zfs",
        "sdb.commands.zfs.internal",
        "sdb.internal",
    ],

    entry_points={
        'console_scripts': ['sdb=sdb.internal.cli:main'],
    },

    author='Delphix Platform Team',
    author_email='serapheim@delphix.com',
    description='The Slick/Simple Debugger',
    license='Apache-2.0',
    url='https://github.com/sdimitro/sdb',
)
