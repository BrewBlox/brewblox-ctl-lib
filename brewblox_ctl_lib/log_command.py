"""
Logs system status and debugging info to file
"""

import shlex
from contextlib import suppress

from brewblox_ctl import utils

from brewblox_ctl_lib import const, lib_utils


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


def add_compose():
    return [
        'echo "==============CONFIG==============" >> brewblox.log',
        'cat docker-compose.yml >> brewblox.log',
    ]


def add_logs():
    sudo = utils.optsudo()
    return [
        'echo "==============LOGS==============" >> brewblox.log',
        'for svc in $({}docker-compose ps --services | tr "\\n" " "); do '.format(sudo) +
        '{}docker-compose logs --timestamps --no-color --tail 200 ${{svc}} >> brewblox.log; '.format(sudo) +
        'echo \'\\n\' >> brewblox.log; ' +
        'done;',
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


def action():
    utils.check_config()

    reason = utils.select('Why are you generating this log? (will be included in log)')

    compose_safe = utils.confirm('Can we include your docker-compose file? ' +
                                 'You should choose "no" if it contains any passwords or other sensitive information')

    shell_commands = [
        *add_header(reason),
        *add_vars(),
        *(add_compose() if compose_safe else []),
        *add_logs(),
        *add_blocks(),
        *add_inspect(),
    ]

    share_commands = [
        'cat brewblox.log | nc termbin.com 9999',
    ]

    utils.run_all(shell_commands)

    if utils.confirm('Do you want to view your log file at <this computer>:9999/brewblox.log?'):
        with suppress(KeyboardInterrupt):
            utils.run('{} -m http.server 9999'.format(const.PY))

    if utils.confirm('Do you want to upload your log file - and get a shareable link?'):
        utils.run_all(share_commands)
