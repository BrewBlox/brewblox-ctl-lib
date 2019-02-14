"""
Const values
"""
import sys

PY = sys.executable

CURRENT_VERSION = '0.2.0'

CONFIG_SRC = './brewblox_ctl_lib/config_files'

DATASTORE_URL = 'https://localhost{}/datastore'
HISTORY_URL = 'https://localhost{}/history'

UI_DATABASE = 'brewblox-ui-store'

CFG_VERSION_KEY = 'BREWBLOX_CFG_VERSION'
RELEASE_KEY = 'BREWBLOX_RELEASE'
HTTP_PORT_KEY = 'BREWBLOX_PORT_HTTP'
HTTPS_PORT_KEY = 'BREWBLOX_PORT_HTTPS'
MDNS_PORT_KEY = 'BREWBLOX_PORT_MDNS'
