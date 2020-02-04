"""
Logs system status and debugging info to file
"""

import shlex
from os import getcwd

import click
from brewblox_ctl import click_helpers, utils

from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


def add_header(reason):
    return [
        'echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log',
        'date >> brewblox.log',
        'echo {} >> brewblox.log'.format(shlex.quote(reason)),
    ]


def add_vars():
    sudo = utils.optsudo()
    vars = {
        k: utils.getenv(k)
        for k in [
            const.RELEASE_KEY,
            const.CFG_VERSION_KEY,
            const.HTTP_PORT_KEY,
            const.HTTPS_PORT_KEY,
            const.MDNS_PORT_KEY,
        ]
    }
    return [
        'echo "==============VARS==============" >> brewblox.log',
        'echo "$(uname -a)" >> brewblox.log',
        'echo "$({}docker --version)" >> brewblox.log'.format(sudo),
        'echo "$({}docker-compose --version)" >> brewblox.log'.format(sudo),
        *[
            'echo "{}={}" >> brewblox.log'.format(key, val)
            for key, val in vars.items()
        ],
    ]


def add_logs():
    sudo = utils.optsudo()
    commands = [
        'echo "==============LOGS==============" >> brewblox.log',
    ]

    try:
        names = list(lib_utils.read_compose()['services'].keys())
        names += list(lib_utils.read_shared_compose()['services'].keys())
        for name in names:
            commands += [
                '{}docker-compose logs --timestamps --no-color --tail 200 {} >> brewblox.log; '.format(sudo, name) +
                'echo \'\\n\' >> brewblox.log; '
            ]
    except Exception as ex:
        commands += [
            'echo {} >> brewblox.log'.format(shlex.quote(type(ex).__name__ + ': ' + str(ex)))
        ]
    return commands


def add_compose():
    return [
        'echo "==============COMPOSE==============" >> brewblox.log',
        'cat docker-compose.yml >> brewblox.log',
        'echo "==============SHARED===============" >> brewblox.log',
        'cat docker-compose.shared.yml >> brewblox.log',
    ]


def add_blocks():
    services = lib_utils.list_services('brewblox/brewblox-devcon-spark')
    base_url = lib_utils.base_url()
    query = '{} http get --pretty {}/{}/objects >> brewblox.log || echo "{} not found" >> brewblox.log'
    return [
        'echo "==============BLOCKS==============" >> brewblox.log',
        *[query.format(const.CLI, base_url, svc, svc) for svc in services]
    ]


def add_inspect():
    sudo = utils.optsudo()
    return [
        'echo "==============INSPECT==============" >> brewblox.log',
        'for cont in $({}docker-compose ps -q); do '.format(sudo) +
        '{}docker inspect $({}docker inspect --format \'{}\' "$cont") >> brewblox.log; '.format(
            sudo, sudo, '{{ .Image }}') +
        'done;',
    ]


@cli.command()
def log():
    """Generate and share log file for bug reports"""
    utils.check_config()

    reason = utils.select('Why are you generating this log? (will be included in log)')

    compose_safe = utils.confirm('Can we include your docker-compose file? ' +
                                 'You should choose "no" if it contains any passwords or other sensitive information')

    shell_commands = [
        *add_header(reason),
        *add_vars(),
        *add_logs(),
        *(add_compose() if compose_safe else []),
        *add_blocks(),
        *add_inspect(),
    ]

    share_commands = [
        'cat brewblox.log | nc termbin.com 9999',
    ]

    utils.run_all(shell_commands)

    print('Generated log file {}/brewblox.log\n'.format(getcwd()))
    if utils.confirm('Do you want to upload your log file to termbin.com to get a shareable link?'):
        utils.run_all(share_commands)
