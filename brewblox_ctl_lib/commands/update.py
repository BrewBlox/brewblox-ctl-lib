"""
Migration scripts
"""

from distutils.version import StrictVersion

import click
from brewblox_ctl import click_helpers, utils

from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def downed_commands(prev_version):
    """Migration commands to be executed while the services are down"""
    if prev_version < StrictVersion('0.2.0'):
        # Breaking changes: Influx downsampling model overhaul
        # Old data is completely incompatible
        utils.select('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                     'We\'ll be deleting it now')
        yield 'sudo rm -rf ./influxdb'

    if prev_version < StrictVersion('0.3.0'):
        # Splitting compose configuration between docker-compose and docker-compose.shared.yml
        # Version pinning (0.2.2) will happen automatically
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
        lib_utils.write_compose(usr_config, 'temp-config.yml')

        for (k, v) in [
            (const.COMPOSE_FILES_KEY, utils.getenv(
                const.COMPOSE_FILES_KEY, 'docker-compose.shared.yml:docker-compose.yml')),
            (const.RELEASE_KEY, utils.getenv(const.RELEASE_KEY, 'stable')),
            (const.HTTP_PORT_KEY, utils.getenv(const.HTTP_PORT_KEY, '80')),
            (const.HTTPS_PORT_KEY, utils.getenv(const.HTTPS_PORT_KEY, '443')),
            (const.MDNS_PORT_KEY, utils.getenv(const.MDNS_PORT_KEY, '5000')),
        ]:
            yield lib_utils.setenv_cmd(k, v)

        yield 'mv ./temp-config.yml ./docker-compose.yml'


def upped_commands(prev_version):
    """Migration commands to be executed after the services have been started"""
    # Always run history configure
    history_url = lib_utils.get_history_url()
    yield '{} http wait {}/ping'.format(const.CLI, history_url)
    yield '{} http post {}/query/configure'.format(const.CLI, history_url)

    # Ensure datastore system databases
    datastore_url = lib_utils.get_datastore_url()
    yield '{} http wait {}'.format(const.CLI, datastore_url)
    yield '{} http put --allow-fail --quiet {}/_users'.format(const.CLI, datastore_url)
    yield '{} http put --allow-fail --quiet {}/_replicator'.format(const.CLI, datastore_url)
    yield '{} http put --allow-fail --quiet {}/_global_changes'.format(const.CLI, datastore_url)
    yield lib_utils.setenv_cmd(const.CFG_VERSION_KEY, const.CURRENT_VERSION)


@cli.command()
@click.option('--update-ctl/--no-update-ctl',
              default=True,
              help='Update brewblox-ctl')
@click.option('--update-ctl-done',
              is_flag=True,
              hidden=True)
@click.option('--pull/--no-pull',
              default=True,
              help='Update Docker service images')
@click.option('--migrate/--no-migrate',
              default=True,
              help='Migrate Brewblox configuration to the new version')
@click.option('--copy-shared/--no-copy-shared',
              default=True,
              help='Reset docker-compose.shared.yml file to default')
@click.option('--prune/--no-prune',
              default=True,
              prompt='Do you want to remove old Docker images to free disk space?',
              help='Prune docker images.')
def update(pull, update_ctl, update_ctl_done, migrate, copy_shared, prune):
    """Update services and configuration"""
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

    def generate():

        if update_ctl and not update_ctl_done:
            yield 'sudo {} -m pip install -U brewblox-ctl'.format(const.PY)
            yield from utils.lib_loading_commands()
            # Restart ctl - we just replaced the source code
            yield ' '.join([const.PY, *const.ARGS, '--update-ctl-done'])
            return

        if pull:
            yield '{}docker-compose pull'.format(sudo)

        if migrate:
            yield from downed_commands(prev_version)

        if copy_shared:
            yield 'cp -f {}/{}/docker-compose.shared.yml ./'.format(const.CONFIG_SRC, lib_utils.config_name())

        yield '{}docker-compose up -d --remove-orphans'.format(sudo)

        if migrate:
            yield from upped_commands(prev_version)

        if prune:
            yield '{}docker image prune -f'.format(sudo)

    utils.run_all(list(generate()))


@cli.command(hidden=True)
@click.option('--prune/--no-prune',
              default=True,
              prompt='Do you want to remove old Docker images to free disk space?',
              help='Prune docker images.')
def migrate(prune):
    """Backwards compatibility implementation to not break brewblox-ctl update"""
    utils.run('{} update --no-pull --no-update-ctl {}'.format(const.CLI, '--prune' if prune else '--no-prune'))
