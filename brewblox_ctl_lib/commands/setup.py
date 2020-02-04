"""
Implementation of brewblox-ctl setup
"""

import click
from brewblox_ctl import click_helpers, utils

from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def check_ports():
    if not utils.confirm('Do you want to check whether ports are already in use?'):
        return

    if utils.path_exists('./docker-compose.yml'):
        utils.run_all([
            '{}docker-compose down --remove-orphans'.format(utils.optsudo())
        ])

    ports = [
        utils.getenv(const.HTTP_PORT_KEY, '80'),
        utils.getenv(const.HTTPS_PORT_KEY, '443'),
        utils.getenv(const.MDNS_PORT_KEY, '5000'),
    ]
    port_commands = [
        'sudo netstat -tulpn | grep ":{}[[:space:]]" || true'.format(port)
        for port in ports
    ]

    utils.announce(port_commands)
    for cmd, port in zip(port_commands, ports):
        print('Checking port {}...'.format(port))
        if utils.check_output(cmd, shell=True) \
                and not utils.confirm('WARNING: port {} is already in use. Do you want to continue?'.format(port)):
            raise SystemExit(0)

    print('Done checking ports. If you want to change the ports used by Brewblox, you can use "brewblox-ctl ports"')


def create_compose():
    return [
        'cp -f {}/{}/* ./'.format(const.CONFIG_SRC, lib_utils.config_name()),
    ]


def create_datastore():
    return [
        'sudo rm -rf ./couchdb/; mkdir ./couchdb/',
    ]


def create_history():
    return [
        'sudo rm -rf ./influxdb/; mkdir ./influxdb/',
    ]


def create_traefik():
    return [
        'sudo rm -rf ./traefik/; mkdir ./traefik/',
        'sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 ' +
        '-subj "/C=NL/ST=./L=./O=Brewblox/OU=./CN=." ' +
        '-keyout traefik/brewblox.key ' +
        '-out traefik/brewblox.crt',
        'sudo chmod 644 traefik/brewblox.crt',
        'sudo chmod 600 traefik/brewblox.key',
    ]


def update():
    sudo = utils.optsudo()
    return [
        '{}docker-compose down --remove-orphans'.format(sudo),
        '{}docker-compose pull'.format(sudo),
    ]


def update_ctl():
    return [
        'sudo {} -m pip install -U brewblox-ctl'.format(const.PY),
    ]


def start_config(images):
    return [
        '{}docker-compose up -d --remove-orphans {}'.format(utils.optsudo(), ' '.join(images)),
    ]


def end_config():
    return [
        '{}docker-compose down'.format(utils.optsudo()),
    ]


def config_datastore():
    shell_commands = []
    modules = ['services', 'dashboards', 'dashboard-items']
    url = lib_utils.get_datastore_url()
    # Basic datastore setup
    shell_commands += [
        '{} http wait {}'.format(const.CLI, url),
        '{} http put {}/_users'.format(const.CLI, url),
        '{} http put {}/_replicator'.format(const.CLI, url),
        '{} http put {}/_global_changes'.format(const.CLI, url),
        '{} http put {}/{}'.format(const.CLI, url, const.UI_DATABASE),
    ]
    # Load presets
    shell_commands += [
        '{} http post {}/{}/_bulk_docs -f {}/presets/{}.json'.format(
            const.CLI, url, const.UI_DATABASE, const.CONFIG_SRC, mod
        )
        for mod in modules
    ]
    return shell_commands


def config_history():
    url = lib_utils.get_history_url()
    return [
        '{} http wait {}/ping'.format(const.CLI, url),
        '{} http post {}/query/configure'.format(const.CLI, url),
    ]


def set_env():
    return [lib_utils.setenv_cmd(*args) for args in [
        (const.COMPOSE_FILES_KEY, utils.getenv(
            const.COMPOSE_FILES_KEY, 'docker-compose.shared.yml:docker-compose.yml')),
        (const.RELEASE_KEY, utils.getenv(const.RELEASE_KEY, 'stable')),
        (const.HTTP_PORT_KEY, utils.getenv(const.HTTP_PORT_KEY, '80')),
        (const.HTTPS_PORT_KEY, utils.getenv(const.HTTPS_PORT_KEY, '443')),
        (const.MDNS_PORT_KEY, utils.getenv(const.MDNS_PORT_KEY, '5000')),
    ]]


@cli.command()
def setup():
    """Run first-time setup"""
    utils.check_config()
    check_ports()

    update_ctl_ok = utils.confirm('Do you want to update brewblox-ctl?')

    setup_compose = \
        not utils.path_exists('./docker-compose.yml') \
        or not utils.confirm('This directory already contains a docker-compose.yml file. ' +
                             'Do you want to keep it?')

    setup_datastore = \
        not utils.path_exists('./couchdb/') \
        or not utils.confirm('This directory already contains datastore files. ' +
                             'Do you want to keep them?')

    setup_history = \
        not utils.path_exists('./influxdb/') \
        or not utils.confirm('This directory already contains history files. ' +
                             'Do you want to keep them?')

    setup_traefik = \
        not utils.path_exists('./traefik/') \
        or not utils.confirm('This directory already contains Traefik files. ' +
                             'Do you want to keep them?')

    shell_commands = []
    config_images = ['traefik', 'influx', 'history']

    shell_commands += set_env()

    if setup_compose:
        shell_commands += create_compose()

    # Update after we're sure we have a compose file
    shell_commands += update()

    if update_ctl_ok:
        shell_commands += update_ctl()

    if setup_datastore:
        config_images += ['datastore']
        shell_commands += create_datastore()

    if setup_history:
        shell_commands += create_history()

    if setup_traefik:
        shell_commands += create_traefik()

    shell_commands += start_config(config_images)

    if setup_datastore:
        shell_commands += config_datastore()

    shell_commands += config_history()
    shell_commands += end_config()

    # Only set version after setup was OK
    shell_commands += [
        '{} {} {}'.format(const.SETENV, const.CFG_VERSION_KEY, const.CURRENT_VERSION),
    ]

    utils.run_all(shell_commands)
    print('All done!')


@cli.command()
@click.option('--http',
              prompt='Which port do you want to use for HTTP connections? Press ENTER to keep using',
              default=lambda: utils.getenv(const.HTTP_PORT_KEY, '80'),
              help='Port used for HTTP connections. Override if default is already in use.')
@click.option('--https',
              prompt='Which port do you want to use for HTTPS connections? Press ENTER to keep using',
              default=lambda: utils.getenv(const.HTTPS_PORT_KEY, '443'),
              help='Port used for HTTPS connections. Override if default is already in use.')
@click.option('--mdns',
              prompt='Which port do you want to use for mDNS discovery? Press ENTER to keep using',
              default=lambda: utils.getenv(const.MDNS_PORT_KEY, '5000'),
              help='Port used for mDNS discovery. Override if default is already in use.')
def ports(http, https, mdns):
    """Update used ports"""
    utils.check_config()

    cfg = {
        const.HTTP_PORT_KEY: http,
        const.HTTPS_PORT_KEY: https,
        const.MDNS_PORT_KEY: mdns,
    }

    shell_commands = [
        '{} {} {}'.format(const.SETENV, key, val)
        for key, val in cfg.items()
    ]

    utils.run_all(shell_commands)
