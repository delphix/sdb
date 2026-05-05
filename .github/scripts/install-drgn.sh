#!/bin/bash -eux

#
# These are build requirements of "drgn"; if we don't install these, the
# build/install of "drgn" will fail below.
#
sudo apt update
sudo apt install bison flex libelf-dev libdw-dev libomp5 libomp-dev

# Install setuptools for Python 3.12+ compatibility
python3 -m pip install --upgrade pip setuptools wheel

git clone https://github.com/osandov/drgn.git

cd drgn
python3 -m pip install .
cd -
