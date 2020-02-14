#!/bin/bash -eux

#
# These are build requirements of "libkdumpfile"; if we don't install these,
# the build/install of "libkdumpfile" will fail below.
#
sudo apt-get install autoconf automake liblzo2-dev libsnappy1v5 libtool pkg-config python3-dev zlib1g-dev

git clone https://github.com/ptesarik/libkdumpfile.git

cd libkdumpfile
autoreconf -fi
./configure --with-python=no
make
sudo make install
cd -
