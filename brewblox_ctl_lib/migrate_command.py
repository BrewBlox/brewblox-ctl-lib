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

    if prev_version < StrictVersion('0.2.2'):
        print('Version pinning docker-compose tags')
        config = lib_utils.read_compose()
        config['services']['datastore']['image'] = 'treehouses/couchdb:2.3.1'
        config['services']['traefik']['image'] = 'traefik:v1.7'
        config['services']['influx']['image'] = 'influxdb:1.7'
        config['services']['ui']['labels'] = [
            'traefik.port=80',
            'traefik.frontend.rule=Path:/, /ui, /ui/{sub:(.*)?}',
        ]
        lib_utils.write_compose(config)

    if prev_version < StrictVersion('0.3.0'):
        print('Moving system services to docker-compose.shared.yml')
        config = lib_utils.read_compose()
        sys_names = [
            'mdns',
            'eventbus',
            'influx',
            'datastore',
            'history',
            'ui',
            'traefik',
        ]
        usr_config = {
            'version': config['version'],
            'services': {key: svc for (key, svc) in config['services'].items() if key not in sys_names}
        }
        sys_config = {
            'version': config['version'],
            'services': {key: svc for (key, svc) in config['services'].items() if key in sys_names}
        }
        lib_utils.write_compose(usr_config, 'temp-config.yml')
        lib_utils.write_compose(sys_config, 'temp-shared.yml')

        shell_commands += [' '.join([const.SETENV, *args]) for args in [
            [const.COMPOSE_FILES_KEY, utils.getenv(
                const.COMPOSE_FILES_KEY, 'docker-compose.shared.yml:docker-compose.yml')],
            [const.RELEASE_KEY, utils.getenv(const.RELEASE_KEY, 'stable')],
            [const.HTTP_PORT_KEY, utils.getenv(const.HTTP_PORT_KEY, '80')],
            [const.HTTPS_PORT_KEY, utils.getenv(const.HTTPS_PORT_KEY, '443')],
            [const.MDNS_PORT_KEY, utils.getenv(const.MDNS_PORT_KEY, '5000')],
        ]]

        shell_commands += [
            'mv ./temp-config.yml ./docker-compose.yml',
            'mv ./temp-shared.yml ./docker-compose.shared.yml',
        ]

    return shell_commands


def upped_commands(prev_version):
    """Migration commands to be executed after the services have been started"""
    shell_commands = []

    # Always run history configure
    history_url = lib_utils.get_history_url()
    shell_commands += [
        '{} http wait {}/ping'.format(const.CLI, history_url),
        '{} http post {}/query/configure'.format(const.CLI, history_url),
    ]

    # Ensure datastore system databases
    datastore_url = lib_utils.get_datastore_url()
    shell_commands += [
        '{} http wait {}'.format(const.CLI, datastore_url),
        '{} http put --allow-fail --quiet {}/_users'.format(const.CLI, datastore_url),
        '{} http put --allow-fail --quiet {}/_replicator'.format(const.CLI, datastore_url),
        '{} http put --allow-fail --quiet {}/_global_changes'.format(const.CLI, datastore_url),
    ]

    if utils.confirm('Do you want to prune unused docker images to free disk space?'):
        shell_commands += [
            '{}docker image prune -f'.format(utils.optsudo())
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
        *downed_commands(prev_version),
        '{}docker-compose up -d'.format(sudo),
        *upped_commands(prev_version),
        '{} {} {}'.format(const.SETENV,
                          const.CFG_VERSION_KEY,
                          const.CURRENT_VERSION),
    ]

    utils.run_all(shell_commands)
