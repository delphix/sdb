#!/bin/bash -eux

#
# Download all the reference core dumps from the public gDrive folder
# and place them in the root directory.
#
python3 -m pip install gdown
gdown --folder 1fdPVuGXbxNKcMEVwhuda04hZTPCcYJms
mv SDB-Public/* .
rmdir SDB-Public
