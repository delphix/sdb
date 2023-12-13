#!/bin/bash -eux

sudo apt update
sudo apt install python3.$(python3 --version | cut -d . -f 2)-dev

#
# Debug statements
#
echo $(which python3)
