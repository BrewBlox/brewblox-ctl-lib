"""
Migration scripts
"""

from distutils.version import StrictVersion

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh
from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def downed_migrate(prev_version):
    """Migration commands to be executed while the services are down"""
    if prev_version < StrictVersion('0.2.0'):
        # Breaking changes: Influx downsampling model overhaul
        # Old data is completely incompatible
        utils.select('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                     'We\'ll be deleting it now')
        sh('sudo rm -rf ./influxdb')

    if prev_version < StrictVersion('0.3.0'):
        # Splitting compose configuration between docker-compose and docker-compose.shared.yml
        # Version pinning (0.2.2) will happen automatically
        utils.info('Moving system services to docker-compose.shared.yml')
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
        lib_utils.write_compose(usr_config)

        utils.info('Writing env values for all variables')
        for key in [
            const.COMPOSE_FILES_KEY,
            const.RELEASE_KEY,
            const.HTTP_PORT_KEY,
            const.HTTPS_PORT_KEY,
            const.MDNS_PORT_KEY,
        ]:
            utils.setenv(key, utils.getenv(key, const.ENV_DEFAULTS[key]))


def upped_migrate(prev_version):
    """Migration commands to be executed after the services have been started"""
    # Always run history configure
    history_url = lib_utils.get_history_url()
    sh('{} http wait {}/ping'.format(const.CLI, history_url))
    sh('{} http post {}/query/configure'.format(const.CLI, history_url))

    # Ensure datastore system databases
    datastore_url = lib_utils.get_datastore_url()
    sh('{} http wait {}'.format(const.CLI, datastore_url))
    sh('{} http put --allow-fail --quiet {}/_users'.format(const.CLI, datastore_url))
    sh('{} http put --allow-fail --quiet {}/_replicator'.format(const.CLI, datastore_url))
    sh('{} http put --allow-fail --quiet {}/_global_changes'.format(const.CLI, datastore_url))
    utils.setenv(const.CFG_VERSION_KEY, const.CURRENT_VERSION)


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
@click.pass_context
def update(ctx, update_ctl, update_ctl_done, pull, migrate, copy_shared, prune):
    """Update services and configuration"""
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()

    prev_version = StrictVersion(utils.getenv(const.CFG_VERSION_KEY, '0.0.0'))

    if prev_version.version == (0, 0, 0):
        click.echo('This configuration was never set up. Please run brewblox-ctl setup first')
        raise SystemExit(1)

    if prev_version > StrictVersion(const.CURRENT_VERSION):
        click.echo('Your system is running a version newer than the selected release. ' +
                   'This may be due to switching release tracks')
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)

    if update_ctl and not update_ctl_done:
        utils.info('Updating brewblox-ctl...')
        sh('sudo {} -m pip install -U brewblox-ctl'.format(const.PY))
        utils.load_ctl_lib()
        # Restart ctl - we just replaced the source code
        sh(' '.join([const.PY, *const.ARGS, '--update-ctl-done']))
        return

    if pull:
        utils.info('Pulling docker images...')
        sh('{}docker-compose pull'.format(sudo))

    if migrate:
        utils.info('Migrating configuration...')
        downed_migrate(prev_version)

    if copy_shared:
        sh('cp -f {}/{}/docker-compose.shared.yml ./'.format(
            const.CONFIG_SRC, lib_utils.config_name()))

    utils.info('Starting docker images...')
    sh('{}docker-compose up -d --remove-orphans'.format(sudo))

    if migrate:
        utils.info('Migrating services...')
        upped_migrate(prev_version)

    if prune:
        utils.info('Pruning unused images...')
        sh('{}docker image prune -f'.format(sudo))


@cli.command(hidden=True)
@click.option('--prune/--no-prune',
              default=True,
              prompt='Do you want to remove old Docker images to free disk space?',
              help='Prune docker images.')
def migrate(prune):
    """Backwards compatibility implementation to not break brewblox-ctl update"""
    sh('{} update --no-pull --no-update-ctl {}'.format(const.CLI, '--prune' if prune else '--no-prune'))
