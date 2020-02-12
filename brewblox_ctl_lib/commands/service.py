"""
User service management
"""

import click
from brewblox_ctl import click_helpers, sh
from brewblox_ctl.commands.docker import restart

from brewblox_ctl_lib import const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def service():
    """Show or edit services in docker-compose.yml."""


def restart_services(ctx):
    if utils.confirm('Do you want to restart your Brewblox services?'):
        ctx.invoke(restart)


@service.command()
@click.option('--image',
              help='Image type filter. Leave blank to show all images.')
@click.option('--file',
              default='docker-compose.yml',
              help='docker-compose configuration file.')
def show(image, file):
    """Show all services of a specific type.

    Use the --image flag to filter."""
    utils.check_config()
    services = utils.list_services(image, file)
    click.echo('\n'.join(services), nl=bool(services))


@service.command()
@click.option('-n', '--name', required=True)
@click.pass_context
def remove(ctx, name):
    """Remove a service."""
    utils.check_config()
    utils.confirm_mode()

    config = utils.read_compose()
    try:
        del config['services'][name]
        utils.info('Removing service \'{}\''.format(name))
        utils.write_compose(config)
        restart_services(ctx)
    except KeyError:
        click.echo('Service \'{}\' not found'.format(name))


@service.command()
@click.option('--port', type=click.INT, default=8300, help='Port on which the editor is served')
@click.pass_context
def editor(ctx, port):
    """Run web-based docker-compose.yml editor.

    This will start a new docker container listening on a host port (default: 8300).
    Navigate there in your browser to access the GUI for editing docker-compose.yml.

    When you're done editing, save your file in the GUI, and press Ctrl+C in the terminal.
    """
    utils.check_config()
    utils.confirm_mode()

    orig = utils.read_file('docker-compose.yml')

    sudo = utils.optsudo()
    host_ip = utils.host_ip()
    editor = 'brewblox/brewblox-web-editor:{}'.format(utils.docker_tag())

    utils.info('Pulling image...')
    sh('{}docker pull {}'.format(sudo, editor))

    try:
        utils.info('Starting editor...')
        sh('{}docker run'.format(sudo) +
           ' --rm --init' +
           ' -p "{}:8300"'.format(port) +
           ' -v "$(pwd):/app/config"' +
           ' {}'.format(editor) +
           ' --host-address {}'.format(host_ip) +
           ' --host-port {}'.format(port))
    except KeyboardInterrupt:  # pragma: no cover
        pass

    if orig != utils.read_file('docker-compose.yml'):
        utils.info('Configuration changes detected.')
        restart_services(ctx)


@service.command()
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
