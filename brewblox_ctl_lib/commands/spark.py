
import click

from brewblox_ctl import click_helpers, const, utils
from brewblox_ctl.utils import sh
from brewblox_ctl_lib import lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def _discover_device(discovery, release, device_host):
    discover_run = '{} discover {} {}'.format(
        const.CLI,
        '--release '.format(release) if release else '',
        '--discovery ' + discovery)

    utils.info('Starting device discovery...')
    devs = [dev for dev in sh(discover_run).split('\n') if dev.rstrip()]

    if not devs:
        click.echo('No devices discovered')
        return

    if device_host:
        for dev in devs:
            if device_host in dev:
                click.echo('Discovered device "{}" matching device host {}'.format(dev, device_host))
                return dev

    for i, dev in enumerate(devs):
        click.echo('device {} :: {}'.format(i+1, dev))

    click.echo('\n')
    idx = -1
    while idx < 1 or idx > len(devs):
        idx = int(utils.select('Which device do you want to use?', '1'))

    return devs[idx-1]


@cli.command()
@click.option('--discovery',
              type=click.Choice(['all', 'usb', 'wifi']),
              default='all',
              help='Discovery setting. Use "all" to check both Wifi and USB')
@click.option('--release',
              default=None,
              help='Brewblox release track')
def discover_spark(discovery, release):
    """
    Discover available Spark controllers.

    This yields device ID for all devices, and IP address for Wifi devices.
    If a device is connected over USB, and has Wifi active, it may show up twice.

    Multicast DNS (mDNS) is used for Wifi discovery. Whether this works is dependent on your router's configuration.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()

    mdns = 'brewblox/brewblox-mdns:{}'.format(utils.docker_tag(release))

    utils.info('Preparing device discovery...')
    sh('{}docker pull {}'.format(sudo, mdns), silent=True)

    utils.info('Discovering devices...')
    sh('{}docker run --net=host -v /dev/serial:/dev/serial --rm -it {} --cli --discovery {}'.format(
        sudo, mdns, discovery))
    utils.info('Done!')


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
    utils.confirm_mode()

    sudo = utils.optsudo()
    config = lib_utils.read_compose()

    if name in config['services'] and not force:
        click.echo('Service "{}" already exists. Use the --force flag if you want to overwrite it'.format(name))
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
    click.echo('Added Spark service \'{}\'.'.format(name))
    click.echo('You can now add it as service in the UI.\n')
    if utils.confirm('Do you want to run \'brewblox-ctl up\' now?'):
        sh('{}docker-compose up -d --remove-orphans'.format(sudo))
