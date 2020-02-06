"""
Logs system status and debugging info to file
"""

import shlex
from os import path

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh
from brewblox_ctl_lib import const, lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


def add_header():
    utils.info('Log file: {}'.format(path.abspath('./brewblox.log')))
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
    utils.info('Writing Brewblox .env values...')
    sh([
        'echo "==============VARS==============" >> brewblox.log',
        'echo "$(uname -a)" >> brewblox.log',
        'echo "$({}docker --version)" >> brewblox.log'.format(sudo),
        'echo "$({}docker-compose --version)" >> brewblox.log'.format(sudo),
    ])
    sh('echo "{}={}" >> brewblox.log'.format(key, val) for key, val in vars.items())


def add_logs():
    sudo = utils.optsudo()
    utils.info('Writing service logs...')
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
    utils.info('Writing docker-compose configuration...')
    sh([
        'echo "==============COMPOSE==============" >> brewblox.log',
        'cat docker-compose.yml >> brewblox.log',
        'echo "==============SHARED===============" >> brewblox.log',
        'cat docker-compose.shared.yml >> brewblox.log',
    ])


def add_blocks():
    services = lib_utils.list_services('brewblox/brewblox-devcon-spark')
    base_url = lib_utils.base_url()

    utils.info('Writing Spark blocks...')
    sh('echo "==============BLOCKS==============" >> brewblox.log')
    query = '{} http get --pretty {}/{}/objects >> brewblox.log || echo "{} not found" >> brewblox.log'
    sh(query.format(const.CLI, base_url, svc, svc) for svc in services)


@cli.command()
@click.option('--skip-compose',
              is_flag=True,
              help='Do not include docker-compose.yml content in log file.')
@click.option('--skip-upload',
              is_flag=True,
              help='Do not upload log file to termbin.com.')
def log(skip_compose, skip_upload):
    """Generate and share log file for bug reports


    \b
    Steps:
        - Create ./brewblox.log file.
        - Append Brewblox .env variables.
        - Append service logs.
        - Append content of docker-compose.yml (optional).
        - Append content of docker-comopse.shared.yml (optional).
        - Append blocks from Spark services.
        - Upload file to termbin.com for shareable link (optional).
    """
    utils.check_config()
    utils.confirm_mode()

    add_header()
    add_vars()
    add_logs()
    if not skip_compose:
        add_compose()
    add_blocks()

    if not skip_upload:
        utils.info('Uploading brewblox.log to termbin.com...')
        sh('cat brewblox.log | nc termbin.com 9999')
