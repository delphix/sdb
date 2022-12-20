#!/bin/bash -eux

#
# These are build requirements of "libkdumpfile"; if we don't install these,
# the build/install of "libkdumpfile" will fail below. Note that we install
# all version of python3.X-dev so the Github actions jobs can install
# libkdumpfile with the right version.
#
sudo apt update
sudo apt install autoconf automake liblzo2-dev libsnappy1v5 libtool pkg-config zlib1g-dev
sudo apt install python3.8-dev python3.9-dev

git clone https://github.com/ptesarik/libkdumpfile.git

cd libkdumpfile
autoreconf -fi
./configure --with-python=$(which python3)
make
sudo make install
cd -

#
# Debug statements
#
echo $(which python3)
