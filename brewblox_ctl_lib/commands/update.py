"""
Migration scripts
"""

from contextlib import suppress
from datetime import datetime
from distutils.version import StrictVersion
from pathlib import Path

import click
import requests
import urllib3
from brewblox_ctl import click_helpers, sh
from brewblox_ctl_lib import const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def apply_config():
    """Apply system-defined configuration from config dir"""
    sh('cp -f {}/traefik-cert.yaml ./traefik/'.format(const.CONFIG_DIR))
    sh('cp -f {}/docker-compose.shared.yml ./'.format(const.CONFIG_DIR))
    shared_cfg = utils.read_shared_compose()
    usr_cfg = utils.read_compose()

    usr_cfg['version'] = shared_cfg['version']
    utils.write_compose(usr_cfg)


def datastore_migrate_redis():
    urllib3.disable_warnings()
    sudo = utils.optsudo()
    opts = utils.ctx_opts()
    redis_url = utils.datastore_url()
    couch_url = 'http://localhost:5984'

    if opts.dry_run:
        utils.info('Dry run. Skipping migration...')
        return

    if not utils.path_exists('./couchdb/'):
        utils.info('couchdb/ dir not found. Skipping migration...')
        return

    utils.info('Starting a temporary CouchDB container on port 5984...')
    sh('{}docker rm -f couchdb-migrate'.format(sudo), check=False)
    sh('{}docker run --rm -d'
        ' --name couchdb-migrate'
        ' -v "$(pwd)/couchdb/:/opt/couchdb/data/"'
        ' -p "5984:5984"'
        ' treehouses/couchdb:2.3.1'.format(sudo))
    sh('{} http wait {}'.format(const.CLI, couch_url))
    sh('{} http wait {}/ping'.format(const.CLI, redis_url))

    resp = requests.get('{}/_all_dbs'.format(couch_url))
    resp.raise_for_status()
    dbs = resp.json()

    for db in ['brewblox-ui-store', 'brewblox-automation']:
        if db in dbs:
            resp = requests.get('{}/{}/_all_docs'.format(couch_url, db),
                                params={'include_docs': True})
            resp.raise_for_status()
            docs = [v['doc'] for v in resp.json()['rows']]
            # Drop invalid names
            docs[:] = [d for d in docs if len(d['_id'].split('__', 1)) == 2]
            for d in docs:
                segments = d['_id'].split('__', 1)
                d['namespace'] = '{}:{}'.format(db, segments[0])
                d['id'] = segments[1]
                del d['_rev']
                del d['_id']
            resp = requests.post('{}/mset'.format(redis_url),
                                 json={'values': docs},
                                 verify=False)
            resp.raise_for_status()
            utils.info('Migrated {} entries from {}'.format(len(docs), db))

    if 'spark-service' in dbs:
        resp = requests.get('{}/spark-service/_all_docs'.format(couch_url),
                            params={'include_docs': True})
        resp.raise_for_status()
        docs = [v['doc'] for v in resp.json()['rows']]
        for d in docs:
            d['namespace'] = 'spark-service'
            d['id'] = d['_id']
            del d['_rev']
            del d['_id']
        resp = requests.post('{}/mset'.format(redis_url),
                             json={'values': docs},
                             verify=False)
        resp.raise_for_status()
        utils.info('Migrated {} entries from spark-service'.format(len(docs)))

    sh('{}docker stop couchdb-migrate'.format(sudo))
    sh('sudo mv couchdb/ couchdb-migrated-{}'.format(datetime.now().strftime('%Y%m%d')))


def migrate_influx_overhaul():
    # Breaking changes: Influx downsampling model overhaul
    # Old data is completely incompatible
    utils.select('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                 "We'll be deleting it now")
    sh('sudo rm -rf ./influxdb')


def migrate_compose_split():
    # Splitting compose configuration between docker-compose and docker-compose.shared.yml
    # Version pinning (0.2.2) will happen automatically
    utils.info('Moving system services to docker-compose.shared.yml...')
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


def migrate_compose_datastore():
    # The couchdb datastore service is gone
    # Older services may still rely on it
    utils.info('Removing `depends_on` fields from docker-compose.yml...')
    config = utils.read_compose()
    for svc in config['services'].values():
        with suppress(KeyError):
            del svc['depends_on']
    utils.write_compose(config)

    # Init dir. It will be filled during upped_migrate
    utils.info('Creating redis/ dir...')
    sh('mkdir -p redis/')


def migrate_ipv6_fix():
    # Undo disable-ipv6
    sh('sudo sed -i "/net.ipv6.*.disable_ipv6 = 1/d" /etc/sysctl.conf', check=False)

    # Enable ipv6 in docker daemon config
    utils.enable_ipv6()


def check_automation_ui():
    # The automation service is deprecated, and its editor is removed from the UI.
    # The service was always optional - only add the automation-ui service if automation is present.
    config = utils.read_compose()
    services = config['services']
    if 'automation' in services and 'automation-ui' not in services:
        utils.info('Adding automation-ui service...')
        services['automation-ui'] = {
            'image': 'brewblox/brewblox-automation-ui:${BREWBLOX_RELEASE}',
            'restart': 'unless-stopped',
        }
        utils.write_compose(config)


def check_env_vars():
    utils.info('Checking .env variables...')
    for (key, default_value) in const.ENV_DEFAULTS.items():
        current_value = utils.getenv(key)
        if current_value is None:
            utils.setenv(key, default_value)


def downed_migrate(prev_version):
    """Migration commands to be executed without any running services"""
    if prev_version < StrictVersion('0.2.0'):
        migrate_influx_overhaul()

    if prev_version < StrictVersion('0.3.0'):
        migrate_compose_split()

    if prev_version < StrictVersion('0.6.0'):
        migrate_compose_datastore()

    if prev_version < StrictVersion('0.6.1'):
        migrate_ipv6_fix()

    # Not related to a specific release
    check_automation_ui()
    check_env_vars()


def upped_migrate(prev_version):
    """Migration commands to be executed after the services have been started"""
    # Always run history configure
    history_url = utils.history_url()
    sh('{} http wait {}/ping'.format(const.CLI, history_url))
    sh('{} http post --quiet {}/configure'.format(const.CLI, history_url))

    if prev_version < StrictVersion('0.6.0'):
        utils.info('Migrating datastore from CouchDB to Redis...')
        datastore_migrate_redis()


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

    --prune/--no-prune. Updates to docker images can leave unused old versions
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
        utils.info('Updating brewblox-ctl libs...')
        utils.load_ctl_lib()
        # Restart ctl - we just replaced the source code
        sh(' '.join([const.PY, *const.ARGS, '--update-ctl-done']))
        return

    if avahi_config:
        utils.update_avahi_config()

    if migrate:
        # Everything except downed_migrate can be done with running services
        utils.info('Stopping services...')
        sh('{}docker-compose down'.format(sudo))

        utils.info('Migrating configuration files...')
        apply_config()
        downed_migrate(prev_version)
    else:
        utils.info('Updating configuration files...')
        apply_config()

    if pull:
        utils.info('Pulling docker images...')
        sh('{}docker-compose pull'.format(sudo))

    utils.info('Starting services...')
    sh('{}docker-compose up -d'.format(sudo))

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
