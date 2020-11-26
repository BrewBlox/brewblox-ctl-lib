"""
Adding and configuring device services
"""

import click
from brewblox_ctl import click_helpers, sh
from brewblox_ctl_lib import const, utils
from brewblox_ctl_lib.discovery import discover_device, find_device


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
@click.option('--discovery', 'discovery_type',
              type=click.Choice(['all', 'usb', 'wifi']),
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
            utils.warn("The existing Spark service '{}' does not have any connection settings.".format(nm))
            utils.warn('It will connect to any controller it can find.')
            utils.warn('This may cause multiple services to connect to the same controller.')
            utils.warn("To reconfigure '{}', please run:".format(nm))
            utils.warn('')
            utils.warn('    brewblox-ctl add-spark -f --name {}'.format(nm))
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
        'image': '{}:{}'.format(image_name, utils.docker_tag(release)),
        'privileged': True,
        'restart': 'unless-stopped',
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

    if name in config['services'] and not force:
        click.echo('Service "{}" already exists. Use the --force flag if you want to overwrite it'.format(name))
        raise SystemExit(1)

    config['services'][name] = {
        'image': 'brewblox/brewblox-plaato:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'environment': {
            'PLAATO_AUTH': token,
        },
        'command': '--name=' + name,
    }

    utils.write_compose(config)
    click.echo("Added Plaato service '{}'.".format(name))
    click.echo('This service publishes history data, but does not have a UI component.')
    if utils.confirm("Do you want to run 'brewblox-ctl up' now?"):
        sh('{}docker-compose up -d --remove-orphans'.format(sudo))


@cli.command()
@click.option('-n', '--name',
              prompt='How do you want to call this service? The name must be unique',
              callback=utils.check_service_name,
              default='node-red',
              help='Service name')
@click.option('-f', '--force',
              is_flag=True,
              help='Allow overwriting an existing service')
def add_node_red(name, force):
    """
    Create a service for Node-RED.
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    host = utils.host_ip()
    port = utils.getenv(const.HTTPS_PORT_KEY)
    config = utils.read_compose()

    if name in config['services'] and not force:
        click.echo('Service "{}" already exists. Use the --force flag if you want to overwrite it'.format(name))
        raise SystemExit(1)

    sh('mkdir -p ./{}'.format(name))
    config['services'][name] = {
        'image': 'brewblox/node-red:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'volumes': [
            './{}:/data'.format(name),
        ]
    }

    utils.write_compose(config)
    click.echo("Added Node-RED service '{}'.".format(name))
    click.echo('Visit https://{}:{}/{} in your browser to load the editor.'.format(host, port, name))
    if utils.confirm("Do you want to run 'brewblox-ctl up' now?"):
        sh('{}docker-compose up -d --remove-orphans'.format(sudo))
