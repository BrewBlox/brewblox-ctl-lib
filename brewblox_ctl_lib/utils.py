"""
Utility functions specific to lib
"""

from brewblox_ctl.utils import getenv

from brewblox_ctl_lib.const import DATASTORE_URL, HISTORY_URL, HTTPS_PORT_KEY


def get_history_url():
    port = getenv(HTTPS_PORT_KEY)
    return HISTORY_URL.format(':' + port if port else '')


def get_datastore_url():
    port = getenv(HTTPS_PORT_KEY)
    return DATASTORE_URL.format(':' + port if port else '')
