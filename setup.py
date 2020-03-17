#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name='sdb',
    version="0.1.0",
    python_requires='>=3.6',
    packages=find_packages(),
    install_requires=[
        'drgn>=0.0.3',
    ],
    entry_points={
        'console_scripts': ['sdb=sdb.internal.cli:main'],
    },
    author='Delphix Platform Team',
    author_email='serapheim@delphix.com',
    description='The Slick Debugger',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/delphix/sdb',
    license='Apache-2.0',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Debuggers",
        "Topic :: System :: Operating System Kernels :: Linux",
    ],
)
