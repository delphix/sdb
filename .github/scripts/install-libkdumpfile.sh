#!/bin/bash -eux

#
# These are build requirements of "libkdumpfile"; if we don't install these,
# the build/install of "libkdumpfile" will fail below. We install python3-dev
# which will work with whatever Python version is set up by actions/setup-python.
#
sudo apt update
sudo apt install autoconf automake liblzo2-dev libsnappy-dev libtool pkg-config zlib1g-dev binutils-dev python3-dev

git clone https://codeberg.org/ptesarik/libkdumpfile.git

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
