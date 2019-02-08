"""
Config-dependent commands
"""

from contextlib import suppress

from brewblox_ctl.commands import Command
from brewblox_ctl.utils import (check_config, confirm, is_pi, path_exists,
                                select)

from brewblox_ctl_lib.const import (CFG_VERSION_KEY, CONFIG_SRC,
                                    CURRENT_VERSION, DATASTORE_URL,
                                    HISTORY_URL, PY, RELEASE_KEY, UI_DATABASE)
from brewblox_ctl_lib.migrate import MigrateCommand


class SetupCommand(Command):
    def __init__(self):
        super().__init__('Run first-time setup', 'setup')

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
            'cp -rf {}/traefik/* ./traefik/'.format(CONFIG_SRC),
            'sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 ' +
            '-keyout traefik/brewblox.key ' +
            '-out traefik/brewblox.crt',
            'sudo chmod 644 traefik/brewblox.crt',
            'sudo chmod 600 traefik/brewblox.key',
        ]

    def update(self):
        return [
            '{}docker-compose down'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
            'sudo {} -m pip install -U brewblox-ctl'.format(PY),
        ]

    def start_config(self, images):
        return [
            '{}docker-compose up -d --remove-orphans {}'.format(self.optsudo, ' '.join(images)),
            'sleep 30',
        ]

    def end_config(self):
        return [
            '{}docker-compose down'.format(self.optsudo),
        ]

    def config_datastore(self):
        shell_commands = []
        modules = ['services', 'dashboards', 'dashboard-items']
        # Basic datastore setup
        shell_commands += [
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE_URL),
            'curl -Sk -X PUT {}/_users'.format(DATASTORE_URL),
            'curl -Sk -X PUT {}/{}'.format(DATASTORE_URL, UI_DATABASE),
        ]
        # Load presets
        shell_commands += [
            'cat {}/presets/{}.json '.format(CONFIG_SRC, mod) +
            '| curl -Sk -X POST ' +
            '--header \'Content-Type: application/json\' ' +
            '--header \'Accept: application/json\' ' +
            '--data "@-" {}/{}/_bulk_docs'.format(DATASTORE_URL, UI_DATABASE)
            for mod in modules
        ]
        return shell_commands

    def config_history(self):
        return [
            'curl -Sk -X GET --retry 60 --retry-delay 10 {}/_service/status > /dev/null'.format(HISTORY_URL),
            'curl -Sk -X POST {}/query/configure'.format(HISTORY_URL),
        ]

    def set_env(self):
        return [
            '{} -m dotenv.cli --quote never set {} {}'.format(PY, CFG_VERSION_KEY, CURRENT_VERSION),
            'echo "All done!"',
        ]

    def action(self):
        check_config()

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
        super().__init__('Import database files', 'import')

    def action(self):
        check_config()

        while True:
            target_dir = select(
                'In which directory can the exported files be found?',
                './brewblox-export'
            ).rstrip('/')

            couchdb_target = target_dir + '/couchdb-snapshot'
            influxdb_target = target_dir + '/influxdb-snapshot'

            if not path_exists(couchdb_target):
                print('"{}" not found'.format(couchdb_target))
            elif not path_exists(influxdb_target):
                print('"{}" not found'.format(influxdb_target))
            else:
                break

        shell_commands = [
            '{}docker-compose up -d influx datastore traefik'.format(self.optsudo),
            'sleep 10',
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE_URL),
            'export PYTHONPATH="./"; {} -m brewblox_ctl_lib.couchdb_backup import {}'.format(PY, couchdb_target),
            '{}docker cp {} $({}docker-compose ps -q influx):/tmp/'.format(
                self.optsudo, influxdb_target, self.optsudo),
            '{}docker-compose exec influx influxd restore -portable /tmp/influxdb-snapshot/'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class ExportCommand(Command):
    def __init__(self):
        super().__init__('Export database files', 'export')

    def action(self):
        check_config()

        target_dir = select(
            'In which directory do you want to place the exported files?',
            './brewblox-export'
        ).rstrip('/')

        couchdb_target = target_dir + '/couchdb-snapshot'
        influxdb_target = target_dir + '/influxdb-snapshot'

        shell_commands = [
            'rm -r {} {} || true'.format(couchdb_target, influxdb_target),
            'mkdir -p {}'.format(couchdb_target),
            'mkdir -p {}'.format(influxdb_target),
            '{}docker-compose up -d influx datastore traefik'.format(self.optsudo),
            'sleep 10',
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE_URL),
            'export PYTHONPATH="./"; {} -m brewblox_ctl_lib.couchdb_backup export {}'.format(
                PY, couchdb_target),
            '{}docker-compose exec influx rm -r /tmp/influxdb-snapshot/ || true'.format(self.optsudo),
            '{}docker-compose exec influx influxd backup -portable /tmp/influxdb-snapshot/'.format(self.optsudo),
            '{}docker cp $({}docker-compose ps -q influx):/tmp/influxdb-snapshot/ {}/'.format(
                self.optsudo, self.optsudo, target_dir),
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
            'echo \'{}\' >> brewblox.log'.format(reason),
        ]

    def add_vars(self):
        return [
            'echo "==============VARS==============" >> brewblox.log',
            'echo "$(uname -a)" >> brewblox.log',
            'echo "$({}docker --version)" >> brewblox.log'.format(self.optsudo),
            'echo "$({}docker-compose --version)" >> brewblox.log'.format(self.optsudo),
            'source .env; echo "{}=${}" >> brewblox.log'.format(RELEASE_KEY, RELEASE_KEY),
            'source .env; echo "{}=${}" >> brewblox.log'.format(CFG_VERSION_KEY, CFG_VERSION_KEY),
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
    SetupCommand(),
    ImportCommand(),
    ExportCommand(),
    CheckStatusCommand(),
    LogFileCommand(),
]
