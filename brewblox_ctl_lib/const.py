"""
Const values
"""
import sys

from brewblox_ctl import const

PY = sys.executable
ARGS = sys.argv
CLI = '{} -m brewblox_ctl'.format(PY)
HOST = 'https://localhost'
DATA_DIR = './brewblox_ctl_lib/data'
CONFIG_DIR = DATA_DIR + '/config'
AVAHI_CONF = '/etc/avahi/avahi-daemon.conf'


UI_DATABASE = 'brewblox-ui-store'

RELEASE_KEY = const.RELEASE_KEY
CFG_VERSION_KEY = const.CFG_VERSION_KEY
HTTP_PORT_KEY = 'BREWBLOX_PORT_HTTP'
HTTPS_PORT_KEY = 'BREWBLOX_PORT_HTTPS'
MQTT_PORT_KEY = 'BREWBLOX_PORT_MQTT'
COMPOSE_FILES_KEY = 'COMPOSE_FILE'
COMPOSE_PROJECT_KEY = 'COMPOSE_PROJECT_NAME'

LOG_SHELL = const.LOG_SHELL
LOG_PYTHON = const.LOG_PYTHON
LOG_ENV = const.LOG_ENV
LOG_COMPOSE = const.LOG_COMPOSE
LOG_INFO = const.LOG_INFO
LOG_WARN = const.LOG_WARN
LOG_ERR = const.LOG_ERR

CURRENT_VERSION = '0.6.1'
ENV_DEFAULTS = {
    RELEASE_KEY: 'edge',
    HTTP_PORT_KEY: '80',
    HTTPS_PORT_KEY: '443',
    MQTT_PORT_KEY: '1883',
    COMPOSE_FILES_KEY: 'docker-compose.shared.yml:docker-compose.yml',
    COMPOSE_PROJECT_KEY: 'brewblox',
}
