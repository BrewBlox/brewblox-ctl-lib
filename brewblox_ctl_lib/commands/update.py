"""
Migration scripts
"""

from distutils.version import StrictVersion
from pathlib import Path

import click
from brewblox_ctl import click_helpers, sh

from brewblox_ctl_lib import const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def apply_shared():
    """Apply docker-compose.shared.yml from data directory"""
    sh('cp -f {}/docker-compose.shared.yml ./'.format(const.CONFIG_DIR))
    shared_cfg = utils.read_shared_compose()
    usr_cfg = utils.read_compose()

    usr_cfg['version'] = shared_cfg['version']
    utils.write_compose(usr_cfg)


def downed_migrate(prev_version):
    """Migration commands to be executed without any running services"""
    if prev_version < StrictVersion('0.2.0'):
        # Breaking changes: Influx downsampling model overhaul
        # Old data is completely incompatible
        utils.select('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                     "We'll be deleting it now")
        sh('sudo rm -rf ./influxdb')

    if prev_version < StrictVersion('0.3.0'):
        # Splitting compose configuration between docker-compose and docker-compose.shared.yml
        # Version pinning (0.2.2) will happen automatically
        utils.info('Moving system services to docker-compose.shared.yml')
        config = utils.read_compose()
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
        utils.write_compose(usr_config)

    utils.info('Checking .env variables')
    for (key, default_value) in const.ENV_DEFAULTS.items():
        current_value = utils.getenv(key)
        if current_value is None:
            utils.setenv(key, default_value)


def upped_migrate(prev_version):
    """Migration commands to be executed after the services have been started"""
    # Always run history configure
    history_url = utils.history_url()
    sh('{} http wait {}/ping'.format(const.CLI, history_url))
    sh('{} http post --quiet {}/query/configure'.format(const.CLI, history_url))

    # Ensure datastore system databases
    datastore_url = utils.datastore_url()
    sh('{} http wait {}'.format(const.CLI, datastore_url))
    sh('{} http put --allow-fail --quiet {}/_users'.format(const.CLI, datastore_url))
    sh('{} http put --allow-fail --quiet {}/_replicator'.format(const.CLI, datastore_url))
    sh('{} http put --allow-fail --quiet {}/_global_changes'.format(const.CLI, datastore_url))


@cli.command()
def libs():
    """Reinstall local libs."""
    utils.confirm_mode()
    utils.load_ctl_lib()


@cli.command()
@click.option('--update-ctl/--no-update-ctl',
              default=True,
              help='Update brewblox-ctl.')
@click.option('--update-ctl-done',
              is_flag=True,
              hidden=True)
@click.option('--pull/--no-pull',
              default=True,
              help='Update docker service images.')
@click.option('--avahi-config/--no-avahi-config',
              default=True,
              help='Update Avahi config to enable mDNS discovery')
@click.option('--migrate/--no-migrate',
              default=True,
              help='Migrate Brewblox configuration and service settings.')
@click.option('--prune/--no-prune',
              default=True,
              prompt='Do you want to remove old docker images to free disk space?',
              help='Remove unused docker images.')
@click.option('--from-version',
              default='0.0.0',
              envvar=const.CFG_VERSION_KEY,
              help='[ADVANCED] Override current version number.')
@click.pass_context
def update(ctx, update_ctl, update_ctl_done, pull, avahi_config, migrate, prune, from_version):
    """Download and apply updates.

    This is the one-stop-shop for updating your Brewblox install.
    You can use any of the options to fine-tune the update by enabling or disabling subroutines.

    By default, all options are enabled.

    --update-ctl/--no-update-ctl determines whether it download new versions
    of brewblox-ctl and brewblox-ctl lib. If this flag is set, update will download the new version
    and then restart itself. This way, the migrate is done with the latest version of brewblox-ctl.

    If you're using dry run mode, you'll notice the hidden option --update-ctl-done.
    You can use it to watch the rest of the update: it\'s a flag to avoid endless loops.

    --pull/--no-pull governs whether new docker images are pulled.
    This is useful if any of your services is using a local image (not from Docker Hub).

    --avahi-config/--no-avahi-config. Check avahi-daemon configuration.
    This is required for TCP discovery of Spark controllers.

    --migrate/--no-migrate. Updates regularly require changes to configuration.
    To do this, services are stopped. If the update only requires pulling docker images,
    you can disable migration to avoid the docker-compose down/up.

    --prune/--no-prune (prompts if not set). Updates to docker images can leave unused old versions
    on your system. These can be pruned to free up disk space.
    Do note that this includes all images on your system, not just those created by Brewblox.

    \b
    Steps:
        - Update brewblox-ctl and extensions.
        - Restart update command to run with updated brewblox-ctl.
        - Pull docker images.
        - Stop services.
        - Migrate configuration files.
        - Copy docker-compose.shared.yml from defaults.
        - Start services.
        - Migrate service configuration.
        - Write version number to .env file.
        - Prune unused images.
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()

    prev_version = StrictVersion(from_version)

    if prev_version.version == (0, 0, 0):
        click.echo('This configuration was never set up. Please run brewblox-ctl setup first')
        raise SystemExit(1)

    if prev_version > StrictVersion(const.CURRENT_VERSION):
        click.echo('Your system is running a version newer than the selected release. ' +
                   'This may be due to switching release tracks.' +
                   'You can use the --from-version flag if you know what you are doing.')
        raise SystemExit(1)

    if Path.home().name != 'root' and Path.home().exists() \
            and Path('/usr/local/bin/brewblox-ctl').exists():  # pragma: no cover
        utils.warn('brewblox-ctl appears to have been installed using sudo.')
        if utils.confirm('Do you want to fix this now?'):
            sh('sudo {} -m pip uninstall -y brewblox-ctl docker-compose'.format(const.PY), check=False)
            utils.pip_install('brewblox-ctl')  # docker-compose is a dependency

            # Debian stretch still has the bug where ~/.local/bin is not included in $PATH
            if '.local/bin' not in utils.getenv('PATH'):
                sh('echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc')

            utils.info('Please run "exec $SHELL --login" to apply the changes to $PATH')
            return

    if update_ctl and not update_ctl_done:
        utils.info('Updating brewblox-ctl...')
        utils.pip_install('brewblox-ctl')
        utils.load_ctl_lib()
        # Restart ctl - we just replaced the source code
        sh(' '.join([const.PY, *const.ARGS, '--update-ctl-done', '--prune' if prune else '--no-prune']))
        return

    utils.info('Updating docker-compose.shared.yml...')
    apply_shared()

    if avahi_config:
        utils.update_avahi_config()

    if migrate:
        # Everything except downed_migrate can be done with running services
        utils.info('Stopping services...')
        sh('{}docker-compose down --remove-orphans'.format(sudo))

        utils.info('Migrating configuration files...')
        downed_migrate(prev_version)

    if pull:
        utils.info('Pulling docker images...')
        sh('{}docker-compose pull'.format(sudo))

    utils.info('Starting services...')
    sh('{}docker-compose up -d --remove-orphans'.format(sudo))

    if migrate:
        utils.info('Migrating service configuration...')
        upped_migrate(prev_version)

        utils.info('Updating version number to {}...'.format(const.CURRENT_VERSION))
        utils.setenv(const.CFG_VERSION_KEY, const.CURRENT_VERSION)

    if prune:
        utils.info('Pruning unused images...')
        sh('{}docker image prune -f'.format(sudo))
        utils.info('Pruning unused volumes...')
        sh('{}docker volume prune -f'.format(sudo))


@cli.command(hidden=True)
@click.option('--prune/--no-prune',
              default=True,
              prompt='Do you want to remove old docker images to free disk space?',
              help='Prune docker images.')
def migrate(prune):
    """Backwards compatibility implementation to not break brewblox-ctl update"""
    sh('{} update --no-pull --no-update-ctl {}'.format(const.CLI, '--prune' if prune else '--no-prune'))
