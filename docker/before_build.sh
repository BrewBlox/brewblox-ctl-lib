#!/usr/bin/env bash
# Automatically executed by CI
set -e

pushd "$(dirname "$(readlink -f "$0")")/.." > /dev/null

mkdir -p docker/source
rm -rf docker/source/*
cp -rf brewblox_ctl_lib/* docker/source/

# recursively clean all pycache/pyc files
find docker/source/ | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf

popd > /dev/null
