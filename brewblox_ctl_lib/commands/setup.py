"""
Implementation of brewblox-ctl setup
"""

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh
from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def check_ports():
    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh('{}docker-compose down --remove-orphans'.format(utils.optsudo()))

    ports = [utils.getenv(key, const.ENV_DEFAULTS[key]) for key in [
        const.HTTP_PORT_KEY,
        const.HTTPS_PORT_KEY,
        const.MDNS_PORT_KEY,
    ]]

    ports_ok = True
    for port in ports:
        if utils.check_ok('sudo netstat -tulpn | grep ":{}[[:space:]]"'.format(port)):
            click.echo('WARNING: port {} is already in use. '.format(port) +
                       'Run "brewblox-ctl ports" to configure Brewblox ports.')
            ports_ok = False

    if not ports_ok \
            and not click.confirm('One or more ports are already in use. Do you want to continue?'):
        raise SystemExit(0)


@cli.command()
@click.option('--port-check/--no-port-check',
              default=True,
              help='Check whether ports are already in use')
def setup(port_check):
    """Run first-time setup"""
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    config_images = ['traefik', 'influx', 'history']
    datastore_url = lib_utils.get_datastore_url()
    history_url = lib_utils.get_history_url()

    if port_check:
        check_ports()

    setup_compose = \
        not utils.path_exists('./docker-compose.yml') \
        or not click.confirm('This directory already contains a docker-compose.yml file. ' +
                             'Do you want to keep it?')

    setup_datastore = \
        not utils.path_exists('./couchdb/') \
        or not click.confirm('This directory already contains datastore files. ' +
                             'Do you want to keep them?')

    setup_history = \
        not utils.path_exists('./influxdb/') \
        or not click.confirm('This directory already contains history files. ' +
                             'Do you want to keep them?')

    setup_gateway = \
        not utils.path_exists('./traefik/') \
        or not click.confirm('This directory already contains Traefik files. ' +
                             'Do you want to keep them?')

    for key, default_val in const.ENV_DEFAULTS:
        utils.info('Setting .env values...')
        utils.setenv(key, utils.getenv(key, default_val))

    if setup_compose:
        utils.info('Copying configuration...')
        sh('cp -f {}/{}/* ./'.format(const.CONFIG_SRC, lib_utils.config_name()))

    # Pull after we're sure we have a compose file
    utils.info('Pulling docker images...')
    sh('{}docker-compose down --remove-orphans'.format(sudo))
    sh('{}docker-compose pull'.format(sudo))

    if setup_datastore:
        utils.info('Creating datastore directory...')
        config_images.append('datastore')
        sh('sudo rm -rf ./couchdb/; mkdir ./couchdb/')

    if setup_history:
        utils.info('Creating history directory...')
        sh('sudo rm -rf ./influxdb/; mkdir ./influxdb/')

    if setup_gateway:
        utils.info('Creating gateway directory...')
        sh('sudo rm -rf ./traefik/; mkdir ./traefik/')

        utils.info('Creating SSL certificate...')
        sh('sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 '
            '-subj "/C=NL/ST=./L=./O=Brewblox/OU=./CN=." '
            '-keyout traefik/brewblox.key '
            '-out traefik/brewblox.crt')
        sh('sudo chmod 644 traefik/brewblox.crt')
        sh('sudo chmod 600 traefik/brewblox.key')

    # Bring images online that we will send configuration
    utils.info('Starting configured services...')
    sh('{}docker-compose up -d --remove-orphans {}'.format(sudo, ' '.join(config_images)))

    if setup_datastore:
        modules = ['services', 'dashboards', 'dashboard-items']
        # Generic datastore setup
        utils.info('Configuring datastore settings...')
        sh('{} http wait {}'.format(const.CLI, datastore_url))
        sh('{} http put {}/_users'.format(const.CLI, datastore_url))
        sh('{} http put {}/_replicator'.format(const.CLI, datastore_url))
        sh('{} http put {}/_global_changes'.format(const.CLI, datastore_url))
        sh('{} http put {}/{}'.format(const.CLI, datastore_url, const.UI_DATABASE))
        # Load presets
        for mod in modules:
            utils.info('Loading preset data...')
            sh('{} http post {}/{}/_bulk_docs -f {}/presets/{}.json'.format(
                const.CLI, datastore_url, const.UI_DATABASE, const.CONFIG_SRC, mod))

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


@cli.command()
@click.option('--http',
              envvar=const.HTTP_PORT_KEY,
              help='Port used for HTTP connections.')
@click.option('--https',
              envvar=const.HTTPS_PORT_KEY,
              help='Port used for HTTPS connections.')
@click.option('--mdns',
              envvar=const.MDNS_PORT_KEY,
              help='Port used for mDNS discovery.')
def ports(http, https, mdns):
    """Update used ports"""
    utils.check_config()
    utils.confirm_mode()

    cfg = {
        const.HTTP_PORT_KEY: http,
        const.HTTPS_PORT_KEY: https,
        const.MDNS_PORT_KEY: mdns,
    }

    utils.info('Writing port settings to .env...')
    for key, val in cfg.items():
        utils.setenv(key, val)
