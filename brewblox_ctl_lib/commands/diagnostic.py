"""
Logs system status and debugging info to file
"""

import shlex
from os import path

import click

from brewblox_ctl import click_helpers, sh
from brewblox_ctl_lib import const, utils

ENV_KEYS = [
    const.RELEASE_KEY,
    const.CFG_VERSION_KEY,
    const.HTTP_PORT_KEY,
    const.HTTPS_PORT_KEY,
    const.MDNS_PORT_KEY,
]


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.command()
@click.option('--add-compose/--no-add-compose',
              default=True,
              help='Include or omit docker-compose config files in the generated log.')
@click.option('--upload/--no-upload',
              default=True,
              help='Whether to upload the log file to termbin.com.')
def log(add_compose, upload):
    """Generate and share log file for bug reports.

    This command generates a comprehensive report on current system state and logs.
    When reporting bugs, a termbin blink to the output is often the first thing asked for.

    For best results, run when the services are still active.
    Service logs are discarded after `brewblox-ctl down`.

    Care is taken to prevent accidental leaks of confidential information.
    Only known variables are read from .env,
    and the `--no-add-compose` flag allows skipping compose configuration.
    The latter is useful if the configuration contains passwords or tokens.

    To review or edit the output, use the `--no-upload` flag.
    The output will include instructions on how to manually upload the file.

    \b
    Steps:
        - Create ./brewblox.log file.
        - Append Brewblox .env variables.
        - Append service logs.
        - Append content of docker-compose.yml (optional).
        - Append content of docker-compose.shared.yml (optional).
        - Append blocks from Spark services.
        - Upload file to termbin.com for shareable link (optional).
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()

    # Create log
    utils.info('Log file: {}'.format(path.abspath('./brewblox.log')))
    sh('echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log')
    sh('date >> brewblox.log')

    # Add .env values
    utils.info('Writing Brewblox .env values...')
    sh('echo "==============VARS==============" >> brewblox.log')
    sh('echo "$(uname -a)" >> brewblox.log')
    sh('echo "$({}docker --version)" >> brewblox.log'.format(sudo))
    sh('echo "$({}docker-compose --version)" >> brewblox.log'.format(sudo))
    sh('echo "{}={}" >> brewblox.log'.format(key, utils.getenv(key)) for key in ENV_KEYS)

    # Add service logs
    utils.info('Writing service logs...')
    sh('echo "==============LOGS==============" >> brewblox.log')
    try:
        names = list(utils.read_compose()['services'].keys())
        names += list(utils.read_shared_compose()['services'].keys())
        raw_cmd = '{}docker-compose logs --timestamps --no-color --tail 200 {} >> brewblox.log; ' + \
            'echo \'\\n\' >> brewblox.log'
        sh(raw_cmd.format(sudo, name) for name in names)
    except Exception as ex:
        sh('echo {} >> brewblox.log'.format(shlex.quote(type(ex).__name__ + ': ' + str(ex))))

    # Add compose config
    if add_compose:
        utils.info('Writing docker-compose configuration...')
        sh('echo "==============COMPOSE==============" >> brewblox.log')
        sh('cat docker-compose.yml >> brewblox.log')
        sh('echo "==============SHARED===============" >> brewblox.log')
        sh('cat docker-compose.shared.yml >> brewblox.log')
    else:
        utils.info('Skipping docker-compose configuration...')

    # Add blocks
    utils.info('Writing Spark blocks...')
    sh('echo "==============BLOCKS==============" >> brewblox.log')
    base_url = utils.base_url()
    services = utils.list_services('brewblox/brewblox-devcon-spark')
    query = '{} http get --pretty {}/{}/objects >> brewblox.log || echo "{} not found" >> brewblox.log'
    sh(query.format(const.CLI, base_url, svc, svc) for svc in services)

    # Upload
    if upload:
        utils.info('Uploading brewblox.log to termbin.com...')
        sh('cat brewblox.log | nc termbin.com 9999')
    else:
        utils.info('Skipping upload. If you want to manually upload the log, run: ' +
                   click.style('cat brewblox.log | nc termbin.com 9999', fg='green'))
