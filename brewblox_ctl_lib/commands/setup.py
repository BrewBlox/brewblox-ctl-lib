"""
Implementation of brewblox-ctl setup
"""

import re

import click
from brewblox_ctl import click_helpers, sh

from brewblox_ctl_lib import const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def check_ports():
    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh('{}docker-compose down --remove-orphans'.format(utils.optsudo()))

    ports = [
        utils.getenv(key, const.ENV_DEFAULTS[key]) for key in [
            const.HTTP_PORT_KEY,
            const.HTTPS_PORT_KEY,
            const.MDNS_PORT_KEY,
        ]]

    utils.info('Checking ports...')
    retv = sh('sudo netstat -tulpn', capture=True)
    lines = retv.split('\n')

    used_ports = []
    used_lines = []
    for port in ports:
        for line in lines:
            if re.match(r'.*(:::|0.0.0.0:){}\s.*'.format(port), line):
                used_ports.append(port)
                used_lines.append(line)
                break

    if used_ports:
        utils.warn('Port(s) {} already in use. '.format(', '.join(used_ports)) +
                   "Run 'brewblox-ctl service ports' to configure Brewblox ports.")
        for line in used_lines:
            utils.warn(line)
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)


@cli.command()
@click.option('--port-check/--no-port-check',
              default=True,
              help='Check whether ports are already in use')
def setup(port_check):
    """Run first-time setup in Brewblox directory.

    Run after brewblox-ctl install, in the newly created Brewblox directory.
    This will create all required configuration files for your system.

    You can safely use this command to partially reset your system.
    Before making any changes, it will check for existing files,
    and prompt if any are found. It will do so separately for docker-compose,
    datastore, history, and gateway files.
    Choose to skip any, and the others will still be created and configured.

    \b
    Steps:
        - Check whether files already exist.
        - Set .env values.
        - Create docker-compose configuration files. (Optional)
        - Pull docker images.
        - Create datastore (CouchDB) directory.      (Optional)
        - Create history (InfluxDB) directory.       (Optional)
        - Create gateway (Traefik) directory.        (Optional)
        - Create SSL certificates.                   (Optional)
        - Start and configure services.              (Optional)
        - Stop all services.
        - Set version number in .env.
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    datastore_url = utils.datastore_url()
    history_url = utils.history_url()
    upped_services = ['traefik', 'influx', 'history']
    preset_modules = ['services', 'dashboards', 'dashboard-items']

    if port_check:
        check_ports()

    skip_compose = \
        utils.path_exists('./docker-compose.yml') \
        and utils.confirm('This directory already contains a docker-compose.yml file. ' +
                          'Do you want to keep it?')

    skip_datastore = \
        utils.path_exists('./couchdb/') \
        and utils.confirm('This directory already contains Couchdb datastore files. ' +
                          'Do you want to keep them?')

    skip_history = \
        utils.path_exists('./influxdb/') \
        and utils.confirm('This directory already contains Influx history files. ' +
                          'Do you want to keep them?')

    skip_gateway = \
        utils.path_exists('./traefik/') \
        and utils.confirm('This directory already contains Traefik gateway files. ' +
                          'Do you want to keep them?')

    utils.info('Setting .env values...')
    for key, default_val in const.ENV_DEFAULTS.items():
        utils.setenv(key, utils.getenv(key, default_val))

    if not skip_compose:
        utils.info('Copying configuration...')
        sh('cp -f {}/* ./'.format(const.CONFIG_DIR))

    # Stop and pull after we're sure we have a compose file
    utils.info('Stopping services...')
    sh('{}docker-compose down --remove-orphans'.format(sudo))
    utils.info('Pulling docker images...')
    sh('{}docker-compose pull'.format(sudo))

    if not skip_datastore:
        utils.info('Creating datastore directory...')
        upped_services.append('datastore')
        sh('sudo rm -rf ./couchdb/; mkdir ./couchdb/')

    if not skip_history:
        utils.info('Creating history directory...')
        sh('sudo rm -rf ./influxdb/; mkdir ./influxdb/')

    if not skip_gateway:
        utils.info('Creating gateway directory...')
        sh('sudo rm -rf ./traefik/; mkdir ./traefik/')

        utils.info('Creating SSL certificate...')
        sh('{}docker run --rm -v "$(pwd)"/traefik/:/certs/ '.format(sudo) +
           'brewblox/omgwtfssl:{}'.format(utils.docker_tag()))
        sh('sudo chmod 644 traefik/brewblox.crt')
        sh('sudo chmod 600 traefik/brewblox.key')

    # Bring images online that we will send configuration
    utils.info('Starting configured services...')
    sh('{}docker-compose up -d --remove-orphans {}'.format(sudo, ' '.join(upped_services)))

    if not skip_datastore:
        # Generic datastore setup
        utils.info('Configuring datastore settings...')
        sh('{} http wait {}'.format(const.CLI, datastore_url))
        sh('{} http put {}/_users'.format(const.CLI, datastore_url))
        sh('{} http put {}/_replicator'.format(const.CLI, datastore_url))
        sh('{} http put {}/_global_changes'.format(const.CLI, datastore_url))
        sh('{} http put {}/{}'.format(const.CLI, datastore_url, const.UI_DATABASE))
        # Load presets
        utils.info('Loading preset data...')
        for mod in preset_modules:
            sh('{} http post {}/{}/_bulk_docs -f {}/{}.json'.format(
                const.CLI, datastore_url, const.UI_DATABASE, const.PRESETS_DIR, mod))

    # Always setup history
    utils.info('Configuring history settings...')
    sh('{} http wait {}/ping'.format(const.CLI, history_url))
    sh('{} http post {}/query/configure'.format(const.CLI, history_url))

    # Setup is done - leave system in stable state
    utils.info('Stopping services...')
    sh('{}docker-compose down'.format(utils.optsudo()))

    # Setup is complete and ok - now set CFG version
    utils.setenv(const.CFG_VERSION_KEY, const.CURRENT_VERSION)
    utils.info('All done!')
