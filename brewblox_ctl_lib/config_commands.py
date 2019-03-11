"""
Config-dependent commands
"""

import shlex
from contextlib import suppress

from brewblox_ctl.commands import Command
from brewblox_ctl.utils import (check_config, check_output, confirm, getenv,
                                is_pi, path_exists, select)

from brewblox_ctl_lib.const import (CFG_VERSION_KEY, CLI, CONFIG_SRC,
                                    CURRENT_VERSION, HTTP_PORT_KEY,
                                    HTTPS_PORT_KEY, MDNS_PORT_KEY, PY,
                                    RELEASE_KEY, UI_DATABASE)
from brewblox_ctl_lib.migrate import MigrateCommand
from brewblox_ctl_lib.utils import get_datastore_url, get_history_url


class PortsCommand(Command):
    def __init__(self):
        super().__init__('Update used ports', 'ports')

    def action(self):
        check_config()

        cfg = {}

        cfg[HTTP_PORT_KEY] = select(
            'Which port do you want to use for HTTP connections?',
            '80'
        )

        cfg[HTTPS_PORT_KEY] = select(
            'Which port do you want to use for HTTPS connections?',
            '443'
        )

        cfg[MDNS_PORT_KEY] = select(
            'Which port do you want to use for discovering Spark controllers?',
            '5000'
        )

        shell_commands = [
            '{} -m dotenv.cli --quote never set {} {}'.format(PY, key, val)
            for key, val in cfg.items()
        ]

        self.run_all(shell_commands)


class SetupCommand(Command):
    def __init__(self):
        super().__init__('Run first-time setup', 'setup')

    def check_ports(self):
        if not confirm('Do you want to check whether ports are already in use?'):
            return

        if path_exists('./docker-compose.yml'):
            self.run_all([
                '{}docker-compose down --remove-orphans'.format(self.optsudo)
            ])

        ports = [
            getenv(HTTP_PORT_KEY, '80'),
            getenv(HTTPS_PORT_KEY, '443'),
            getenv(MDNS_PORT_KEY, '5000'),
        ]
        port_commands = [
            'sudo netstat -tulpn | grep ":{}[[:space:]]" || true'.format(port)
            for port in ports
        ]

        self.announce(port_commands)
        for cmd, port in zip(port_commands, ports):
            print('Checking port {}...'.format(port))
            if check_output(cmd, shell=True) \
                    and not confirm('WARNING: port {} is already in use. Do you want to continue?'.format(port)):
                raise SystemExit(0)

        print('Done checking ports. If you want to change the ports used by BrewBlox, you can use "brewblox-ctl ports"')

    def create_compose(self):
        return [
            'cp -f {}/{} ./docker-compose.yml'.format(
                CONFIG_SRC,
                'docker-compose_{}.yml'.format('armhf' if is_pi() else 'amd64')
            ),
        ]

    def create_datastore(self):
        return [
            'sudo rm -rf ./couchdb/; mkdir ./couchdb/',
        ]

    def create_history(self):
        return [
            'sudo rm -rf ./influxdb/; mkdir ./influxdb/',
        ]

    def create_traefik(self):
        return [
            'sudo rm -rf ./traefik/; mkdir ./traefik/',
            'sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 ' +
            '-keyout traefik/brewblox.key ' +
            '-out traefik/brewblox.crt',
            'sudo chmod 644 traefik/brewblox.crt',
            'sudo chmod 600 traefik/brewblox.key',
        ]

    def update(self):
        return [
            '{}docker-compose down --remove-orphans'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
        ]

    def update_ctl(self):
        return [
            'sudo {} -m pip install -U brewblox-ctl'.format(PY),
        ]

    def start_config(self, images):
        return [
            '{}docker-compose up -d --remove-orphans {}'.format(self.optsudo, ' '.join(images)),
        ]

    def end_config(self):
        return [
            '{}docker-compose down'.format(self.optsudo),
        ]

    def config_datastore(self):
        shell_commands = []
        modules = ['services', 'dashboards', 'dashboard-items']
        url = get_datastore_url()
        # Basic datastore setup
        shell_commands += [
            '{} http wait {}'.format(CLI, url),
            '{} http put {}/_users'.format(CLI, url),
            '{} http put {}/{}'.format(CLI, url, UI_DATABASE),
        ]
        # Load presets
        shell_commands += [
            '{} http post {}/{}/_bulk_docs -f {}/presets/{}.json'.format(
                CLI, url, UI_DATABASE, CONFIG_SRC, mod
            )
            for mod in modules
        ]
        return shell_commands

    def config_history(self):
        url = get_history_url()
        return [
            '{} http wait {}/_service/status'.format(CLI, url),
            '{} http post {}/query/configure'.format(CLI, url),
        ]

    def set_env(self):
        return [
            '{} -m dotenv.cli --quote never set {} {}'.format(PY, CFG_VERSION_KEY, CURRENT_VERSION),
            'echo "All done!"',
        ]

    def action(self):
        check_config()
        self.check_ports()

        update_ctl = confirm('Do you want to update brewblox-ctl?')

        setup_compose = \
            not path_exists('./docker-compose.yml') \
            or not confirm('This directory already contains a docker-compose.yml file. ' +
                           'Do you want to keep it?')

        setup_datastore = \
            not path_exists('./couchdb/') \
            or not confirm('This directory already contains datastore files. ' +
                           'Do you want to keep them?')

        setup_history = \
            not path_exists('./influxdb/') \
            or not confirm('This directory already contains history files. ' +
                           'Do you want to keep them?')

        setup_traefik = \
            not path_exists('./traefik/') \
            or not confirm('This directory already contains Traefik files. ' +
                           'Do you want to keep them?')

        shell_commands = []
        config_images = ['traefik']

        if setup_compose:
            shell_commands += self.create_compose()

        # Update after we're sure we have a compose file
        shell_commands += self.update()

        if update_ctl:
            shell_commands += self.update_ctl()

        if setup_datastore:
            config_images += ['datastore']
            shell_commands += self.create_datastore()

        if setup_history:
            config_images += ['influx', 'history']
            shell_commands += self.create_history()

        if setup_traefik:
            shell_commands += self.create_traefik()

        if setup_history or setup_datastore:
            # Start configuration of running containers
            shell_commands += self.start_config(config_images)

            if setup_datastore:
                shell_commands += self.config_datastore()

            if setup_history:
                shell_commands += self.config_history()

            shell_commands += self.end_config()

        # Only set version after setup was OK
        shell_commands += self.set_env()

        self.run_all(shell_commands)


class UpdateCommand(Command):
    def __init__(self):
        super().__init__('Update services and scripts', 'update')

    def action(self):
        check_config()
        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
            'sudo {} -m pip install -U brewblox-ctl'.format(PY),
            *self.lib_commands(),
            '{} -m brewblox_ctl migrate'.format(PY),
        ]
        self.run_all(shell_commands)

        print('Scripts were updated - brewblox-ctl must shut down now')
        raise SystemExit(0)


class ImportCommand(Command):
    def __init__(self):
        super().__init__('Import datastore files', 'import')

    def action(self):
        check_config()

        target_dir = select(
            'In which directory can the exported files be found?',
            './brewblox-export'
        ).rstrip('/')

        shell_commands = [
            '{}docker-compose up -d datastore traefik'.format(self.optsudo),
            '{} http wait {}'.format(CLI, get_datastore_url()),
            'export PYTHONPATH="./"; {} -m brewblox_ctl_lib.couchdb_backup import {}'.format(PY, target_dir),
        ]
        self.run_all(shell_commands)


class ExportCommand(Command):
    def __init__(self):
        super().__init__('Export datastore files', 'export')

    def action(self):
        check_config()

        target_dir = select(
            'In which directory do you want to place the exported files?',
            './brewblox-export'
        ).rstrip('/')

        shell_commands = [
            'mkdir -p {}'.format(target_dir),
            '{}docker-compose up -d datastore traefik'.format(self.optsudo),
            '{} http wait {}'.format(CLI, get_datastore_url()),
            'export PYTHONPATH="./"; {} -m brewblox_ctl_lib.couchdb_backup export {}'.format(
                PY, target_dir),
        ]
        self.run_all(shell_commands)


class CheckStatusCommand(Command):
    def __init__(self):
        super().__init__('Check system status', 'status')

    def action(self):
        check_config()
        shell_commands = [
            'echo "Your release track is \\"${}\\""; '.format(RELEASE_KEY) +
            'echo "Your config version is \\"${}\\""; '.format(CFG_VERSION_KEY) +
            '{}docker-compose ps'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class LogFileCommand(Command):
    def __init__(self):
        super().__init__('Generate and share log file for bug reports', 'log')

    def add_header(self, reason):
        return [
            'echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log',
            'date >> brewblox.log',
            'echo {} >> brewblox.log'.format(shlex.quote(reason)),
        ]

    def add_vars(self):
        vars = {
            k: getenv(k)
            for k in [
                RELEASE_KEY,
                CFG_VERSION_KEY,
                HTTP_PORT_KEY,
                HTTPS_PORT_KEY,
                MDNS_PORT_KEY,
            ]
        }
        return [
            'echo "==============VARS==============" >> brewblox.log',
            'echo "$(uname -a)" >> brewblox.log',
            'echo "$({}docker --version)" >> brewblox.log'.format(self.optsudo),
            'echo "$({}docker-compose --version)" >> brewblox.log'.format(self.optsudo),
            *[
                'echo "{}={}" >> brewblox.log'.format(key, val)
                for key, val in vars.items()
            ],
        ]

    def add_compose(self):
        return [
            'echo "==============CONFIG==============" >> brewblox.log',
            'cat docker-compose.yml >> brewblox.log',
        ]

    def add_logs(self):
        return [
            'echo "==============LOGS==============" >> brewblox.log',
            'for svc in $({}docker-compose ps --services | tr "\\n" " "); do '.format(self.optsudo) +
            '{}docker-compose logs --timestamps --no-color --tail 200 ${{svc}} >> brewblox.log; '.format(self.optsudo) +
            'echo \'\\n\' >> brewblox.log; ' +
            'done;',
        ]

    def add_inspect(self):
        return [
            'echo "==============INSPECT==============" >> brewblox.log',
            'for cont in $({}docker-compose ps -q); do '.format(self.optsudo) +
            '{}docker inspect $({}docker inspect --format \'{}\' "$cont") >> brewblox.log; '.format(
                self.optsudo, self.optsudo, '{{ .Image }}') +
            'done;',
        ]

    def action(self):
        check_config()

        reason = select('Why are you generating this log? (will be included in log)')

        compose_safe = confirm('Can we include your docker-compose file? ' +
                               'You should choose "no" if it contains any passwords or other sensitive information')

        shell_commands = [
            *self.add_header(reason),
            *self.add_vars(),
            *(self.add_compose() if compose_safe else []),
            *self.add_logs(),
            *self.add_inspect(),
        ]

        share_commands = [
            'cat brewblox.log | nc termbin.com 9999',
        ]

        self.run_all(shell_commands)

        if confirm('Do you want to view your log file at <this computer>:9999/brewblox.log?'):
            with suppress(KeyboardInterrupt):
                self.run('{} -m http.server 9999'.format(PY))

        if confirm('Do you want to upload your log file - and get a shareable link?'):
            self.run_all(share_commands)


ALL_COMMANDS = [
    UpdateCommand(),
    MigrateCommand(),
    PortsCommand(),
    SetupCommand(),
    ImportCommand(),
    ExportCommand(),
    CheckStatusCommand(),
    LogFileCommand(),
]
