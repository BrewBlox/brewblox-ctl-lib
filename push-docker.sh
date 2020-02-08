#! /usr/bin/env bash
set -e

# The build script generated a :local tagged image
# This script retags and pushes that image
# To keep in sync with other brewblox images, we're also pushing an "rpi-" prefixed image, even if it's the same
#
# Argument is the tag name they should be pushed as
# Leave this blank to set it to the git branch name

CLEAN_BRANCH_NAME=$(echo "${TRAVIS_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}" | tr '/' '-' | tr '[:upper:]' '[:lower:]');
REPO=brewblox/brewblox-ctl-lib
TAG=${1:-${CLEAN_BRANCH_NAME}}

# rpi- tags are no longer needed for ctl-lib
# Keep them around for backwards compatibility
docker tag ${REPO}:local ${REPO}:${TAG}
docker tag ${REPO}:local ${REPO}:rpi-${TAG}

docker push ${REPO}:${TAG}
docker push ${REPO}:rpi-${TAG}
echo "pushed ${TAG} / rpi-${TAG}"
