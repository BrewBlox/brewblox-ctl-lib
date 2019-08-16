"""
Utility functions specific to lib
"""

import yaml
from brewblox_ctl.utils import getenv

from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY


def base_url():
    port = getenv(HTTPS_PORT_KEY, '443')
    return '{}:{}'.format(HOST, port)


def get_history_url():
    return '{}/history'.format(base_url())


def get_datastore_url():
    return '{}/datastore'.format(base_url())


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())


def list_services(image, fname='docker-compose.yml'):
    with open(fname) as f:
        config = yaml.safe_load(f)

    return [
        k for k, v in config['services'].items()
        if v.get('image', '').startswith(image)
    ]
