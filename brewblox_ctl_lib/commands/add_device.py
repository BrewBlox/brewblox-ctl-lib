"""
Adding and configuring device services
"""

from os import getgid, getuid

import click
from brewblox_ctl import click_helpers, sh
from brewblox_ctl_lib import const, utils
from brewblox_ctl_lib.discovery import discover_device, find_device


def check_duplicate(config: dict, name: str):
    if name in config['services'] \
            and not utils.confirm(f'Service `{name}` already exists. Do you want to overwrite it?'):
        raise SystemExit(1)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
@click.option('--discovery', 'discovery_type',
              type=click.Choice(['all', 'usb', 'wifi', 'lan']),
              default='all',
              help='Discovery setting. Use "all" to check both Wifi and USB')
def discover_spark(discovery_type):
    """
    Discover available Spark controllers.

    This prints device ID for all devices, and IP address for Wifi devices.
    If a device is connected over USB, and has Wifi active, it may show up twice.

    Multicast DNS (mDNS) is used for Wifi discovery.
    Whether this works is dependent on the configuration of your router and avahi-daemon.
    """
    for dev in discover_device(discovery_type):
        utils.info(dev['desc'])
    utils.info('Done!')


@cli.command()
@click.option('-n', '--name',
              prompt='How do you want to call this service? The name must be unique',
              callback=utils.check_service_name,
              help='Service name')
@click.option('--discover-now/--no-discover-now',
              default=True,
              help='Select from discovered devices if --device-id is not set')
@click.option('--device-id',
              help='Checked device ID')
@click.option('--discovery', 'discovery_type',
              type=click.Choice(['all', 'usb', 'wifi', 'lan']),
              default='all',
              help='Discovery setting. Use "all" to check both LAN and USB')
@click.option('--device-host',
              help='Static controller URL')
@click.option('-c', '--command',
              help='Additional arguments to pass to the service command')
@click.option('-f', '--force',
              is_flag=True,
              help='Allow overwriting an existing service')
@click.option('--release',
              default='${BREWBLOX_RELEASE}',
              help='Brewblox release track used by the Spark service.')
@click.option('--simulation',
              is_flag=True,
              help='Add a simulation service. This will override discovery and connection settings.')
def add_spark(name,
              discover_now,
              device_id,
              discovery_type,
              device_host,
              command,
              force,
              release,
              simulation):
    """
    Create or update a Spark service.

    If you run brewblox-ctl add-spark without any arguments,
    it will prompt you for required info, and then create a sensibly configured service.

    If you want to fine-tune your service configuration, multiple arguments are available.

    For a detailed explanation: https://brewblox.netlify.com/user/connect_settings.html
    """
    utils.check_config()
    utils.confirm_mode()

    image_name = 'brewblox/brewblox-devcon-spark'
    sudo = utils.optsudo()
    config = utils.read_compose()

    if not force:
        check_duplicate(config, name)

    for (nm, svc) in config['services'].items():
        img = svc.get('image', '')
        cmd = svc.get('command', '')
        if not any([
            nm == name,
            not img.startswith(image_name),
            '--device-id' in cmd,
            '--device-host' in cmd,
            '--simulation' in cmd,
        ]):
            utils.warn(f'The existing Spark service `{nm}` does not have any connection settings.')
            utils.warn('It will connect to any controller it can find.')
            utils.warn('This may cause multiple services to connect to the same controller.')
            utils.warn(f'To reconfigure `{nm}`, please run:')
            utils.warn('')
            utils.warn(f'    brewblox-ctl add-spark -f --name {nm}')
            utils.warn('')
            utils.select('Press ENTER to continue or Ctrl-C to exit')

    if device_id is None and discover_now and not simulation:
        dev = find_device(discovery_type, device_host)

        if dev:
            device_id = dev['id']
        elif device_host is None:
            # We have no device ID, and no device host. Avoid a wildcard service
            click.echo('No valid combination of device ID and device host.')
            raise SystemExit(1)

    commands = [
        '--name=' + name,
        '--discovery=' + discovery_type,
    ]

    if device_id:
        commands += ['--device-id=' + device_id]

    if device_host:
        commands += ['--device-host=' + device_host]

    if simulation:
        commands += ['--simulation']

    if command:
        commands += [command]

    config['services'][name] = {
        'image': f'{image_name}:{utils.docker_tag(release)}',
        'privileged': True,
        'restart': 'unless-stopped',
        'command': ' '.join(commands)
    }

    if simulation:
        volume_dir = f'simulator__{name}'
        config['services'][name]['volumes'] = [
            f'./{volume_dir}:/app/simulator'
        ]
        sh(f'mkdir -m 777 -p {volume_dir}')

    utils.write_compose(config)
    click.echo(f'Added Spark service `{name}`.')
    click.echo('It will automatically show up in the UI.\n')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        sh(f'{sudo}docker-compose up -d')


@cli.command()
@click.option('-f', '--force',
              is_flag=True,
              help='Allow overwriting an existing service')
def add_tilt(force):
    """
    Create a service for the Tilt hydrometer.

    The service listens for Bluetooth status updates from the Tilt,
    and requires the host to have a Bluetooth receiver.

    The empty ./tilt dir is created to hold calibration files.
    """
    utils.check_config()
    utils.confirm_mode()

    name = 'tilt'
    sudo = utils.optsudo()
    config = utils.read_compose()

    if not force:
        check_duplicate(config, name)

    config['services'][name] = {
        'image': 'brewblox/brewblox-tilt:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'privileged': True,
        'network_mode': 'host',
        'volumes': [
            f'./{name}:/share',
        ],
        'labels': [
            'traefik.enable=false',
        ],
    }

    sh(f'mkdir -p ./{name}')

    utils.write_compose(config)
    click.echo(f'Added Tilt service `{name}`.')
    click.echo('It will automatically show up in the UI.\n')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        sh(f'{sudo}docker-compose up -d')


@cli.command()
@click.option('-n', '--name',
              prompt='How do you want to call this service? The name must be unique',
              callback=utils.check_service_name,
              default='plaato',
              help='Service name')
@click.option('--token',
              prompt='What is your Plaato auth token? '
              'For more info: https://plaato.io/apps/help-center#!hc-auth-token',
              help='Plaato authentication token.')
@click.option('-f', '--force',
              is_flag=True,
              help='Allow overwriting an existing service')
def add_plaato(name, token, force):
    """
    Create a service for the Plaato airlock.

    This will periodically query the Plaato server for current state.
    An authentication token is required.

    See https://plaato.io/apps/help-center#!hc-auth-token on how to get one.
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    config = utils.read_compose()

    if not force:
        check_duplicate(config, name)

    config['services'][name] = {
        'image': 'brewblox/brewblox-plaato:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'environment': {
            'PLAATO_AUTH': token,
        },
        'command': f'--name={name}',
    }

    utils.write_compose(config)
    click.echo(f'Added Plaato service `{name}`.')
    click.echo('This service publishes history data, but does not have a UI component.')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        sh(f'{sudo}docker-compose up -d')


@cli.command()
@click.option('-f', '--force',
              is_flag=True,
              help='Allow overwriting an existing service')
def add_node_red(force):
    """
    Create a service for Node-RED.
    """
    utils.check_config()
    utils.confirm_mode()

    name = 'node-red'
    sudo = utils.optsudo()
    host = utils.host_ip()
    port = utils.getenv(const.HTTPS_PORT_KEY)
    config = utils.read_compose()

    if not force:
        check_duplicate(config, name)

    config['services'][name] = {
        'image': 'brewblox/node-red:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'volumes': [
            f'./{name}:/data',
        ]
    }

    sh(f'mkdir -p ./{name}')
    if [getgid(), getuid()] != [1000, 1000]:
        sh(f'sudo chown -R 1000:1000 ./{name}')

    utils.write_compose(config)
    click.echo(f'Added Node-RED service `{name}`.')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        sh(f'{sudo}docker-compose up -d')
        click.echo(f'Visit https://{host}:{port}/{name} in your browser to load the editor.')
