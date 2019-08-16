"""
Utility functions specific to lib
"""

from brewblox_ctl.utils import getenv

from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY


def get_history_url():
    port = getenv(HTTPS_PORT_KEY, '443')
    return '{}:{}/history'.format(HOST, port)


def get_datastore_url():
    port = getenv(HTTPS_PORT_KEY, '443')
    return '{}:{}/datastore'.format(HOST, port)


def get_spark_one_url():
    port = getenv(HTTPS_PORT_KEY, '443')
    return '{}:{}/spark-one'.format(HOST, port)


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())
