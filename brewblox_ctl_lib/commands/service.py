"""
User service management
"""


import sys
from subprocess import DEVNULL, check_call

import click
from brewblox_ctl import click_helpers, const, utils

from brewblox_ctl_lib import lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def service():
    """Commands for adding, removing and editing services"""


def _discover_device(discovery, release, device_host):
    discover_run = '{} discover {} {}'.format(
        const.CLI,
        '--release ' + release if release else '',
        '--discovery ' + discovery)

    print('Starting device discovery...')
    devs = [dev for dev in utils.subcommand(discover_run).split('\n') if dev.rstrip()]

    if not devs:
        print('No devices discovered')
        return

    if device_host:
        for dev in devs:
            if device_host in dev:
                print('Discovered device "{}" matching device host {}'.format(dev, device_host))
                return dev

    for i, dev in enumerate(devs):
        print('device', i+1, '::', dev)

    print('\n')
    idx = -1
    while idx < 1 or idx > len(devs):
        idx = int(utils.select('Which device do you want to use?', '1'))

    return devs[idx-1]


@cli.command()
@click.option('--discovery',
              type=click.Choice(['all', 'usb', 'wifi']),
              default='all',
              help='Discovery setting. Use "all" to check both Wifi and USB')
@click.option('--release', default=None, help='Brewblox release track')
@click.option('--announce', is_flag=True, help='Display running commands')
def discover_spark(discovery, release, announce):
    """
    Discover available Spark controllers.

    This yields device ID for all devices, and IP address for Wifi devices.
    If a device is connected over USB, and has Wifi active, it may show up twice.

    Multicast DNS (mDNS) is used for Wifi discovery. Whether this works is dependent on your router's configuration.
    """
    sudo = utils.optsudo()
    mdns = 'brewblox/brewblox-mdns:{}'.format(utils.docker_tag(release))
    commands = [
        '{}docker pull {}'.format(sudo, mdns),
        '{}docker run --net=host -v /dev/serial:/dev/serial --rm -it {} --cli --discovery {}'.format(
            sudo, mdns, discovery)
    ]

    if announce:
        utils.run_all(commands)
    else:
        print('Preparing device discovery...', file=sys.stderr)
        check_call(commands[0], shell=True, stdout=DEVNULL)
        print('Discovering devices...', file=sys.stderr)
        check_call(commands[1], shell=True)


@cli.command()
@click.option('-n', '--name',
              prompt='How do you want to call this service? The name must be unique',
              callback=lib_utils.check_service_name,
              help='Service name')
@click.option('--discover-now/--no-discover-now',
              default=True,
              help='Select from discovered devices if --device-id is not set')
@click.option('--device-id',
              help='Check for device ID')
@click.option('--discovery',
              type=click.Choice(['all', 'usb', 'wifi']),
              default='all',
              help='Discovery setting. Use "all" to check both Wifi and USB')
@click.option('--device-host',
              help='Static controller URL')
@click.option('-c', '--command',
              help='Additional arguments to pass to the service command')
@click.option('-f', '--force',
              is_flag=True,
              help='Allow overwriting an existing service')
@click.option('--release',
              help='Brewblox release track used by the discovery container.')
def add_spark(name, discover_now, device_id, discovery, device_host, command, force, release):
    """
    Create or update a Spark service.

    If you run brewblox-ctl add-spark without any arguments,
    it will prompt you for required info, and then create a sensibly configured service.

    If you want to fine-tune your service configuration, multiple arguments are available.

    For a detailed explanation: https://brewblox.netlify.com/user/connect_settings.html
    """
    utils.check_config()
    config = lib_utils.read_compose()

    if name in config['services'] and not force:
        print('Service "{}" already exists. Use the --force flag if you want to overwrite it'.format(name))
        return

    if device_id is None and device_host is None and discover_now:
        dev = _discover_device(discovery, release, device_host)

        if dev:
            device_id = dev.split(' ')[1]
        else:
            return

    commands = [
        '--name=' + name,
        '--mdns-port=${BREWBLOX_PORT_MDNS}',
        '--discovery=' + discovery,
    ]

    if device_id:
        commands += ['--device-id=' + device_id]

    if device_host:
        commands += ['--device-host=' + device_host]

    if command:
        commands += [command]

    config['services'][name] = {
        'image': 'brewblox/brewblox-devcon-spark:{}'.format(utils.docker_tag('${BREWBLOX_RELEASE}')),
        'privileged': True,
        'restart': 'unless-stopped',
        'labels': [
            'traefik.port=5000',
            'traefik.frontend.rule=PathPrefix: /{}'.format(name),
        ],
        'command': ' '.join(commands)
    }

    lib_utils.write_compose(config)
    print('Added Spark service "{}".'.format(name))
    print('You can now add it as service in the UI.\n')
    if utils.confirm('Do you want to run "brewblox-ctl up" now?'):
        utils.run('{} up'.format(const.CLI))


@service.command()
@click.option('--image')
@click.option('--file', default='docker-compose.yml')
def show(image, file):
    """Show all services of a specific type. Use the --image flag to filter."""
    utils.check_config()
    services = lib_utils.list_services(image, file)
    click.echo('\n'.join(services), nl=bool(services))


@service.command()
@click.option('-n', '--name', required=True)
def remove(name):
    """Remove a user service."""
    utils.check_config()
    config = lib_utils.read_compose()
    try:
        del config['services'][name]
        lib_utils.write_compose(config)
        click.echo('Removed service \'{}\''.format(name))
    except KeyError:
        click.echo('Service \'{}\' not found'.format(name))


@service.command()
@click.option('--port', type=click.INT, default=8300, help='Port on which the editor is served')
def editor(port):
    """Run web-based docker-compose.yml editor"""
    utils.check_config()
    orig = lib_utils.read_file('docker-compose.yml')

    sudo = utils.optsudo()
    host_ip = lib_utils.get_host_url()
    editor = 'brewblox/brewblox-web-editor:{}'.format(utils.docker_tag())
    editor_commands = [
        # Pull
        '{}docker pull {}'.format(sudo, editor),
        # Run
        '{}docker run'.format(sudo) +
        ' --rm --init' +
        ' -p "{}:8300"'.format(port) +
        ' -v "$(pwd):/app/config"' +
        ' {}'.format(editor) +
        ' --host-address {}'.format(host_ip) +
        ' --host-port {}'.format(port),
    ]

    try:
        utils.run_all(editor_commands)
    except KeyboardInterrupt:
        pass

    if orig != lib_utils.read_file('docker-compose.yml') \
        and utils.confirm('Configuration changes detected. '
                          'Do you want to restart your Brewblox services?'):
        utils.run('{} restart'.format(const.CLI))
