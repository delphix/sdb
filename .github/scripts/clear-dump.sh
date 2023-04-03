#!/bin/bash -eu

DATA_DIR="tests/integration/data"

echo "checking folder structure ..."
if [ ! -d $DATA_DIR ]; then
	exit 1
fi

echo "removing all crash/core dumps ..."
rm -rf $DATA_DIR/dumps

echo "Done"
