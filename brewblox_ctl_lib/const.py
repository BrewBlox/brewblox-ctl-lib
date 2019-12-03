"""
Const values
"""
import sys

PY = sys.executable
CLI = '{} -m brewblox_ctl'.format(PY)
SETENV = '{} -m dotenv.cli --quote never set'.format(PY)

CURRENT_VERSION = '0.3.0'

CONFIG_SRC = './brewblox_ctl_lib/config_files'

HOST = 'https://localhost'

UI_DATABASE = 'brewblox-ui-store'

CFG_VERSION_KEY = 'BREWBLOX_CFG_VERSION'
RELEASE_KEY = 'BREWBLOX_RELEASE'
HTTP_PORT_KEY = 'BREWBLOX_PORT_HTTP'
HTTPS_PORT_KEY = 'BREWBLOX_PORT_HTTPS'
MDNS_PORT_KEY = 'BREWBLOX_PORT_MDNS'

COMPOSE_FILES_KEY = 'COMPOSE_FILE'
