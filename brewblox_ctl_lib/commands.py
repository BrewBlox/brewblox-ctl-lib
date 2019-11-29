"""
Config-dependent commands
"""


import re
from subprocess import DEVNULL, check_call

import click
from brewblox_ctl import click_helpers, utils

from brewblox_ctl_lib import (const, lib_utils, log_command, migrate_command,
                              setup_command)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
def ports():
    """Update used ports"""
    utils.check_config()

    cfg = {}

    cfg[const.HTTP_PORT_KEY] = utils.select(
        'Which port do you want to use for HTTP connections?',
        '80'
    )

    cfg[const.HTTPS_PORT_KEY] = utils.select(
        'Which port do you want to use for HTTPS connections?',
        '443'
    )

    cfg[const.MDNS_PORT_KEY] = utils.select(
        'Which port do you want to use for discovering Spark controllers?',
        '5000'
    )

    shell_commands = [
        '{} -m dotenv.cli --quote never set {} {}'.format(const.PY, key, val)
        for key, val in cfg.items()
    ]

    utils.run_all(shell_commands)


@cli.command()
def setup():
    """Run first-time setup"""
    setup_command.action()


@cli.command()
def update():
    """Update services and scripts"""
    utils.check_config()
    sudo = utils.optsudo()
    shell_commands = [
        '{}docker-compose down'.format(sudo),
        '{}docker-compose pull'.format(sudo),
        'sudo {} -m pip install -U brewblox-ctl'.format(const.PY),
        *utils.lib_loading_commands(),
        '{} migrate'.format(const.CLI),
    ]

    utils.run_all(shell_commands)


@cli.command()
def migrate():
    """Update configuration files to the lastest version"""
    migrate_command.action()


@cli.command()
@click.option('--port', type=click.INT, default=8300, help='Port on which the editor is served')
def editor(port):
    """Run web-based docker-compose.yml editor"""
    utils.check_config()
    orig = lib_utils.read_file('docker-compose.yml')

    sudo = utils.optsudo()
    editor = 'brewblox/brewblox-web-editor:{}'.format(utils.docker_tag())
    editor_commands = [
        '{}docker pull {}'.format(sudo, editor),
        '{}docker run --rm --init -p "{}:8300" -v "$(pwd):/app/config" {} --hostPort {}'.format(
            sudo,
            port,
            editor,
            port
        )
    ]

    try:
        utils.run_all(editor_commands)
    except KeyboardInterrupt:
        pass

    if orig != lib_utils.read_file('docker-compose.yml') \
        and utils.confirm('Configuration changes detected. '
                          'Do you want to restart your BrewBlox services?'):
        utils.run_all([
            '{} restart'.format(const.CLI),
        ], prompt=False)


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--announce', is_flag=True, help='Display running commands')
def discover(release, announce):
    sudo = utils.optsudo()
    mdns = 'brewblox/brewblox-mdns:{}'.format(utils.docker_tag(release))
    commands = [
        '{}docker pull {}'.format(sudo, mdns),
        '{}docker run --net=host -v /dev/serial:/dev/serial --rm -it {} --cli'.format(sudo, mdns)
    ]

    if announce:
        utils.run_all(commands)
    else:
        check_call(commands[0], shell=True, stdout=DEVNULL)
        check_call(commands[1], shell=True)


def _validate_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain letters, numbers, - or _')
    return value


def _discover_device(release, device_host):
    discover_run = '{} discover {}'.format(const.CLI, '--release ' + release if release else '')

    print('Discovering devices...')
    devs = [dev for dev in lib_utils.subcommand(discover_run).split('\n') if dev.rstrip()]

    if not devs:
        print('No devices discovered')
        return

    if device_host:
        dev = next((dev for dev in devs if device_host in dev), None)  # pragma: no cover
        if dev:
            print('Discovered device "{}" matching device host {}'.format(dev, device_host))
            return dev

    for i, dev in enumerate(devs):
        print('device', i+1, '::', dev)

    print('\n')
    idx = -1
    while idx < 1 or idx > len(devs):
        idx = int(utils.select('Which device do you want to use? Press ENTER for default value', '1'))

    return devs[idx-1]


@cli.command()
@click.option('-n', '--name',
              prompt='Service name',
              callback=_validate_name,
              help='Service name')
@click.option('--discover/--no-discover',
              default=True,
              help='Discover devices if device ID is not supplied')
@click.option('--device-id',
              help='Check for device ID')
@click.option('--discovery',
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
              default=None,
              help='BrewBlox release track used by the discovery container.')
def add_spark(name, discover, device_id, discovery, device_host, command, force, release):
    utils.check_config()
    config = lib_utils.read_compose()

    if name in config['services'] and not force:
        print('Service "{}" already exists. Use the --force flag if you want to overwrite it'.format(name))
        return

    if device_id is None and discover:
        dev = _discover_device(release, device_host)

        if not dev:
            return

        args = dev.split(' ')
        device_id = args[1]
        if args[0] == 'wifi' \
            and not device_host \
                and utils.confirm('A Wifi device was chosen: do you want to use its URL as --device-host?'):
            device_host = args[2]

    commands = [
        '--name=' + name,
        '--mdns-port=${BREWBLOX_PORT_MDNS:-5000}',
        '--discovery=' + discovery,
    ]

    if device_id:
        commands += ['--device-id=' + device_id]

    if device_host:
        commands += ['--device-host=' + device_host]

    if command:
        commands += [command]

    config['services'][name] = {
        'image': 'brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE:-stable}',
        'privileged': 'true',
        'restart': 'unless-stopped',
        'labels': [
            '"traefik.port=5000"',
            '"traefik.frontend.rule=PathPrefix: /{}"'.format(name),
        ],
        'command': ' '.join(commands)
    }

    lib_utils.write_compose(config)
    print('Added Spark service "{}".'.format(name))
    print('You can now add it as service in the UI.\n')
    if utils.confirm('Do you want to restart your services now?'):
        utils.run('{} restart'.format(const.CLI))


@cli.command()
def status():
    """Check system status"""
    utils.check_config()
    shell_commands = [
        'echo "Your release track is \\"${}\\""; '.format(const.RELEASE_KEY) +
        'echo "Your config version is \\"${}\\""; '.format(const.CFG_VERSION_KEY) +
        '{}docker-compose ps'.format(utils.optsudo()),
    ]
    utils.run_all(shell_commands)


@cli.command()
def log():
    """Generate and share log file for bug reports"""
    log_command.action()


@cli.command()
@click.option('--image', default='brewblox/brewblox-devcon-spark')
@click.option('--file', default='docker-compose.yml')
def list_services(image, file):
    """List all services of a specific type"""
    utils.check_config()
    services = lib_utils.list_services(image, file)
    click.echo('\n'.join(services), nl=bool(services))
