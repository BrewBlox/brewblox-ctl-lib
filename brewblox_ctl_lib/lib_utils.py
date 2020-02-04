"""
Utility functions specific to lib
"""

import re
from subprocess import check_output

import click
import yaml
from brewblox_ctl.utils import getenv, is_pi

from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY, SETENV


def base_url():
    port = getenv(HTTPS_PORT_KEY, '443')
    return '{}:{}'.format(HOST, port)


def get_history_url():
    return '{}/history'.format(base_url())


def get_datastore_url():
    return '{}/datastore'.format(base_url())


def config_name():
    return 'armhf' if is_pi() else 'amd64'


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())


def read_compose(fname='docker-compose.yml'):
    with open(fname) as f:
        return yaml.safe_load(f)


def write_compose(config, fname='docker-compose.yml'):  # pragma: no cover
    with open(fname, 'w') as f:
        yaml.safe_dump(config, f)


def read_shared_compose(fname='docker-compose.shared.yml'):
    return read_compose(fname)


def write_shared_compose(config, fname='docker-compose.shared.yml'):  # pragma: no cover
    write_compose(config, fname)


def list_services(image=None, fname=None):
    config = read_compose(fname) if fname else read_compose()

    return [
        k for k, v in config['services'].items()
        if image is None or v.get('image', '').startswith(image)
    ]


def subcommand(cmd):  # pragma: no cover
    return check_output(cmd, shell=True).decode()


def setenv_cmd(key, value):
    return '{} {} {}'.format(SETENV, key, value)


def check_service_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain lowercase letters, numbers, - or _')
    return value


def get_host_url():
    try:
        # remote IP / port, local IP / port
        return getenv('SSH_CONNECTION', '').split()[2]
    except IndexError:
        return '127.0.0.1'
