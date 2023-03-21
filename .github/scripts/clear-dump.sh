#!/bin/bash -eu

DATA_DIR="tests/integration/data"

echo "checking folder structure ..."
if [ ! -d $DATA_DIR ]; then
	exit 1
fi

echo "removing current crash dump if any ..."
rm -f $DATA_DIR/dump.*

echo "removing any extracted vmlinux ..."
rm -f $DATA_DIR/vmlinux*

echo "removing any extracted modules ..."
rm -rf $DATA_DIR/mods
rm -rf $DATA_DIR/usr

echo "removing any savedump scripts ..."
rm -rf $DATA_DIR/run-*.sh

echo "Done"
