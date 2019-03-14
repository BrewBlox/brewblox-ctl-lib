"""
Migration scripts
"""

from distutils.version import StrictVersion

from brewblox_ctl.commands import Command
from brewblox_ctl.utils import check_config, confirm, getenv, select

from brewblox_ctl_lib.const import CFG_VERSION_KEY, CLI, CURRENT_VERSION, PY
from brewblox_ctl_lib.utils import get_history_url


class MigrateCommand(Command):
    def __init__(self):
        super().__init__('Run migration scripts against current configuration', 'migrate')
        self.prev_version = None

    def downed_commands(self):
        """Migration commands to be executed while the services are down"""
        shell_commands = []

        if self.prev_version < StrictVersion('0.2.0'):
            # Breaking changes: Influx downsampling model overhaul
            # Old data is completely incompatible
            select('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                   'We\'ll be deleting it now')
            shell_commands += ['sudo rm -rf ./influxdb']

        return shell_commands

    def upped_commands(self):
        """Migration commands to be executed after the services have been started"""
        shell_commands = []

        # Always run history configure
        history_url = get_history_url()
        shell_commands += [
            '{} http wait {}/_service/status'.format(CLI, history_url),
            '{} http post {}/query/configure'.format(CLI, history_url),
        ]

        return shell_commands

    def action(self):
        check_config()
        self.prev_version = StrictVersion(getenv(CFG_VERSION_KEY, '0.0.0'))

        if self.prev_version.version == (0, 0, 0):
            print('This configuration was never set up. Please run brewblox-ctl setup first')
            raise SystemExit(1)

        if self.prev_version == StrictVersion(CURRENT_VERSION):
            print('Your system already is running the latest version ({})'.format(CURRENT_VERSION))
            return

        if self.prev_version >= StrictVersion(CURRENT_VERSION):
            print('Your system is running a version later than the latest. ' +
                  'This may be due to switching release tracks')
            if not confirm('Do you want to continue?'):
                raise SystemExit(1)

        shell_commands = [
            '{}docker-compose down --remove-orphans'.format(self.optsudo),
            *self.downed_commands(),
            '{}docker-compose up -d'.format(self.optsudo),
            *self.upped_commands(),
            '{} -m dotenv.cli --quote never set {} {}'.format(PY, CFG_VERSION_KEY, CURRENT_VERSION),
        ]

        self.run_all(shell_commands)
