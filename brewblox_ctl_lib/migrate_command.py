"""
Migration scripts
"""

from distutils.version import StrictVersion

from brewblox_ctl import utils
from brewblox_ctl_lib import const, lib_utils


def downed_commands(prev_version):
    """Migration commands to be executed while the services are down"""
    shell_commands = []

    if prev_version < StrictVersion('0.2.0'):
        # Breaking changes: Influx downsampling model overhaul
        # Old data is completely incompatible
        utils.select('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                     'We\'ll be deleting it now')
        shell_commands += ['sudo rm -rf ./influxdb']

    return shell_commands


def upped_commands():
    """Migration commands to be executed after the services have been started"""
    shell_commands = []

    # Always run history configure
    history_url = lib_utils.get_history_url()
    shell_commands += [
        '{} http wait {}/ping'.format(const.CLI, history_url),
        '{} http post {}/query/configure'.format(const.CLI, history_url),
    ]

    return shell_commands


def action():
    utils.check_config()
    sudo = utils.optsudo()
    prev_version = StrictVersion(utils.getenv(const.CFG_VERSION_KEY, '0.0.0'))

    if prev_version.version == (0, 0, 0):
        print('This configuration was never set up. Please run brewblox-ctl setup first')
        raise SystemExit(1)

    if prev_version > StrictVersion(const.CURRENT_VERSION):
        print('Your system is running a version newer than the selected release. ' +
              'This may be due to switching release tracks')
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)

    shell_commands = [
        '{}docker-compose down --remove-orphans'.format(sudo),
        *downed_commands(),
        '{}docker-compose up -d'.format(sudo),
        *upped_commands(),
        '{} -m dotenv.cli --quote never set {} {}'.format(const.PY,
                                                          const.CFG_VERSION_KEY,
                                                          const.CURRENT_VERSION),
    ]

    utils.run_all(shell_commands)
