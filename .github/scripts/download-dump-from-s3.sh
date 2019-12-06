#!/bin/bash -eu

#
# Assumptions for this to work:
# [1] This script is executed from the root of the SDB repo
# [2] The archive downloaded from S3 is lzma-compressed
# [3] The archive's contents have the following hierarchy:
#           dump-data
#           ├── dump.201912060006
#           ├── mods
#           │   ├── avl
#           │   │   └── zavl.ko
#           .....
#           │   └── zfs
#           │       └── zfs.ko
#           └── vmlinux-5.0.0-36-generic
#

DATA_DIR="tests/integration/data"

echo "checking folder structure ..."
if [ ! -d $DATA_DIR ]; then
	exit 1
fi

echo "initiating download of $1 from S3 ..."
/usr/local/bin/aws s3 cp --no-sign-request s3://sdb-regression-dumps/$1 .
[ $? -eq 0 ]  || exit 1

echo "decompressing dump ..."
tar -x --lzma -f $1

echo "moving contents to tests/integration/data ..."
mv dump-data/* $DATA_DIR
[ $? -eq 0 ]  || exit 1

rmdir dump-data
[ $? -eq 0 ]  || exit 1

echo "Done"
