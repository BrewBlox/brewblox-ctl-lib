
import re
from glob import glob
from queue import Empty, Queue
from socket import inet_ntoa

import click
from brewblox_ctl import click_helpers, sh
from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

from brewblox_ctl_lib import utils

BREWBLOX_DNS_TYPE = '_brewblox._tcp.local.'
DISCOVER_TIMEOUT_S = 5


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def discover_usb():
    lines = '\n'.join([f for f in glob('/dev/serial/by-id/*')])
    for obj in re.finditer(r'particle_(?P<model>p1|photon)_(?P<serial>[a-z0-9]+)-',
                           lines,
                           re.IGNORECASE | re.MULTILINE):
        id = obj.group('serial')
        model = obj.group('model')
        # 'usb ' is same length as 'wifi'
        desc = 'usb  {} {}'.format(id, model)
        yield {
            'id': id,
            'desc': desc,
            'model': model,
        }


def discover_wifi():
    queue = Queue()
    conf = Zeroconf()

    def on_service_state_change(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            queue.put(info)

    try:
        ServiceBrowser(conf, BREWBLOX_DNS_TYPE, handlers=[on_service_state_change])
        while True:
            info = queue.get(timeout=DISCOVER_TIMEOUT_S)
            if not info or not info.addresses or info.addresses == [b'\x00\x00\x00\x00']:
                continue  # discard simulators
            id = info.server[:-len('.local.')]
            host = inet_ntoa(info.addresses[0])
            port = info.port
            desc = 'wifi {} {} {}'.format(id, host, port)
            yield {
                'id': id,
                'desc': desc,
                'host': host,
                'port': port,
            }
    except Empty:
        pass
    finally:
        conf.close()


def discover_device(discovery):
    utils.info('Discovering devices...')
    if discovery in ['all', 'usb']:
        yield from discover_usb()
    if discovery in ['all', 'wifi']:
        yield from discover_wifi()


def find_device(discovery, device_host=None):
    devs = []

    for i, dev in enumerate(discover_device(discovery)):
        if not device_host:
            devs.append(dev)
            click.echo('device {} :: {}'.format(i+1, dev['desc']))

        # Don't echo discarded devices
        if device_host and dev.get('host') == device_host:
            click.echo('{} matches --device-host {}'.format(dev['desc'], device_host))
            return dev

    if device_host or not devs:
        click.echo('No devices discovered')
        return None

    idx = click.prompt('Which device do you want to use?',
                       type=click.IntRange(1, len(devs)),
                       default=1)

    return devs[idx-1]


@cli.command()
@click.option('--discovery',
              type=click.Choice(['all', 'usb', 'wifi']),
              default='all',
              help='Discovery setting. Use "all" to check both Wifi and USB')
def discover_spark(discovery):
    """
    Discover available Spark controllers.

    This prints device ID for all devices, and IP address for Wifi devices.
    If a device is connected over USB, and has Wifi active, it may show up twice.

    Multicast DNS (mDNS) is used for Wifi discovery.
    Whether this works is dependent on the configuration of your router and avahi-daemon.
    """
    for dev in discover_device(discovery):
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
              default='${BREWBLOX_RELEASE}',
              help='Brewblox release track used by the Spark service.')
@click.option('--simulation',
              is_flag=True,
              help='Add a simulation service. This will override discovery and connection settings.')
def add_spark(name,
              discover_now,
              device_id,
              discovery,
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

    if name in config['services'] and not force:
        click.echo('Service "{}" already exists. Use the --force flag if you want to overwrite it'.format(name))
        raise SystemExit(1)

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
            utils.warn("The Spark service '{}' does not have any connection settings".format(nm))
            utils.warn('This may cause multiple services to connect to the same controller.')
            utils.warn('To fix, please run:')
            utils.warn('')
            utils.warn('    brewblox-ctl add-spark -f --name {}'.format(nm))
            utils.warn('')
            utils.select('Press ENTER to continue')

    if device_id is None and discover_now and not simulation:
        dev = find_device(discovery, device_host)

        if dev:
            device_id = dev['id']
        elif device_host is None:
            # We have no device ID, and no device host. Avoid a wildcard service
            click.echo('No valid combination of device ID and device host.')
            raise SystemExit(1)

    commands = [
        '--name=' + name,
        '--discovery=' + discovery,
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
        'image': '{}:{}'.format(image_name, utils.docker_tag(release)),
        'privileged': True,
        'restart': 'unless-stopped',
        'labels': [
            'traefik.port=5000',
            'traefik.frontend.rule=PathPrefix: /{}'.format(name),
        ],
        'command': ' '.join(commands)
    }

    if simulation:
        volume_dir = 'simulator__{}'.format(name)
        config['services'][name]['volumes'] = [
            './{}:/app/simulator'.format(volume_dir)
        ]
        sh('mkdir -m 777 -p {}'.format(volume_dir))

    utils.write_compose(config)
    click.echo("Added Spark service '{}'.".format(name))
    click.echo('It will automatically show up in the UI.\n')
    if utils.confirm("Do you want to run 'brewblox-ctl up' now?"):
        sh('{}docker-compose up -d --remove-orphans'.format(sudo))
