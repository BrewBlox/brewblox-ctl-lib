"""
User service management
"""

import click

from brewblox_ctl import click_helpers, sh
from brewblox_ctl_lib import const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def service():
    """Commands for adding, removing and editing services"""


@service.command()
@click.option('--image',
              help='Image type filter. Leave blank to show all images.')
@click.option('--file',
              default='docker-compose.yml',
              help='docker-compose configuration file.')
def show(image, file):
    """Show all services of a specific type. Use the --image flag to filter."""
    utils.check_config()
    services = utils.list_services(image, file)
    click.echo('\n'.join(services), nl=bool(services))


@service.command()
@click.option('-n', '--name', required=True)
def remove(name):
    """Remove a user service."""
    utils.check_config()
    utils.confirm_mode()

    config = utils.read_compose()
    try:
        del config['services'][name]
        utils.info('Removing service \'{}\''.format(name))
        utils.write_compose(config)
    except KeyError:
        click.echo('Service \'{}\' not found'.format(name))


@service.command()
@click.option('--port', type=click.INT, default=8300, help='Port on which the editor is served')
def editor(port):
    """Run web-based docker-compose.yml editor"""
    utils.check_config()
    utils.confirm_mode()

    orig = utils.read_file('docker-compose.yml')

    sudo = utils.optsudo()
    host_ip = utils.get_host_ip()
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

    if orig != utils.read_file('docker-compose.yml') \
        and utils.confirm('Configuration changes detected. '
                          'Do you want to restart your Brewblox services?'):
        sh('{} restart'.format(const.CLI))
