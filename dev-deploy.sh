#! /usr/bin/env bash

# Copies the brewblox_ctl_lib dir to current working directory
# This allows manual testing without the hassle of building docker images
# Will croak if current working directory is the root code directory

SCRIPT_DIR=$(readlink -f $(dirname "${BASH_SOURCE[0]}"))

if [ "${SCRIPT_DIR}" = "$(pwd)" ]; then
    echo "Script and CWD are the same. Exiting."
    exit
fi

rm -rf ./brewblox_ctl_lib
cp -r ${SCRIPT_DIR}/brewblox_ctl_lib ./
find ./brewblox_ctl_lib/ | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf
