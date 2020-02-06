"""
Logs system status and debugging info to file
"""

import shlex
from os import getcwd

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh
from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


def add_header():
    sh('echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log')
    sh('date >> brewblox.log')


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
    sh([
        'echo "==============VARS==============" >> brewblox.log',
        'echo "$(uname -a)" >> brewblox.log',
        'echo "$({}docker --version)" >> brewblox.log'.format(sudo),
        'echo "$({}docker-compose --version)" >> brewblox.log'.format(sudo),
    ])
    sh('echo "{}={}" >> brewblox.log'.format(key, val) for key, val in vars.items())


def add_logs():
    sudo = utils.optsudo()
    sh('echo "==============LOGS==============" >> brewblox.log')

    try:
        names = list(lib_utils.read_compose()['services'].keys())
        names += list(lib_utils.read_shared_compose()['services'].keys())
        for name in names:
            sh('{}docker-compose logs --timestamps --no-color --tail 200 {} >> brewblox.log; '.format(sudo, name) +
                'echo \'\\n\' >> brewblox.log; ')
    except Exception as ex:
        sh('echo {} >> brewblox.log'.format(shlex.quote(type(ex).__name__ + ': ' + str(ex))))


def add_compose():
    sh([
        'echo "==============COMPOSE==============" >> brewblox.log',
        'cat docker-compose.yml >> brewblox.log',
        'echo "==============SHARED===============" >> brewblox.log',
        'cat docker-compose.shared.yml >> brewblox.log',
    ])


def add_blocks():
    services = lib_utils.list_services('brewblox/brewblox-devcon-spark')
    base_url = lib_utils.base_url()
    sh('echo "==============BLOCKS==============" >> brewblox.log')
    query = '{} http get --pretty {}/{}/objects >> brewblox.log || echo "{} not found" >> brewblox.log'
    sh(query.format(const.CLI, base_url, svc, svc) for svc in services)


def add_inspect():
    sudo = utils.optsudo()
    sh([
        'echo "==============INSPECT==============" >> brewblox.log',
        'for cont in $({}docker-compose ps -q); do '.format(sudo) +
        '{}docker inspect $({}docker inspect --format \'{}\' "$cont") >> brewblox.log; '.format(
            sudo, sudo, '{{ .Image }}') +
        'done;',
    ])


@cli.command()
def log():
    """Generate and share log file for bug reports"""
    click.get_current_context().ensure_object(dict)['dry'] = True
    utils.check_config()

    compose_safe = utils.confirm('Can we include your docker-compose file? ' +
                                 'You should choose "no" if it contains any passwords or other sensitive information')

    add_header()
    add_vars()
    add_logs()
    if compose_safe:
        add_compose()
    add_blocks()
    add_inspect()

    click.echo('Generated log file {}/brewblox.log\n'.format(getcwd()))
    if utils.confirm('Do you want to upload your log file to termbin.com to get a shareable link?'):
        sh('cat brewblox.log | nc termbin.com 9999')
