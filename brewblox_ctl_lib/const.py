"""
Const values
"""
import sys

CURRENT_VERSION = '0.3.0'

PY = sys.executable
CLI = '{} -m brewblox_ctl'.format(PY)
ARGS = sys.argv
HOST = 'https://localhost'
CONFIG_SRC = './brewblox_ctl_lib/config_files/'
UI_DATABASE = 'brewblox-ui-store'

CFG_VERSION_KEY = 'BREWBLOX_CFG_VERSION'
RELEASE_KEY = 'BREWBLOX_RELEASE'
HTTP_PORT_KEY = 'BREWBLOX_PORT_HTTP'
HTTPS_PORT_KEY = 'BREWBLOX_PORT_HTTPS'
MDNS_PORT_KEY = 'BREWBLOX_PORT_MDNS'
COMPOSE_FILES_KEY = 'COMPOSE_FILE'

ENV_DEFAULTS = {
    RELEASE_KEY: 'stable',
    HTTP_PORT_KEY: '80',
    HTTPS_PORT_KEY: '443',
    MDNS_PORT_KEY: '5000',
    COMPOSE_FILES_KEY: 'docker-compose.shared.yml:docker-compose.yml',
}
