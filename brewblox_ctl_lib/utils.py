"""
Utility functions specific to lib
"""

import json
import re

import click
import yaml
from brewblox_ctl import utils

from brewblox_ctl_lib import const

# Module-level __getattr__ is reintroduced in 3.7
# There are some hacks, but for now dumb is better than convoluted
ctx_opts = utils.ctx_opts
confirm = utils.confirm
select = utils.select
confirm_usb = utils.confirm_usb
confirm_mode = utils.confirm_mode
getenv = utils.getenv
setenv = utils.setenv
path_exists = utils.path_exists
command_exists = utils.command_exists
is_pi = utils.is_pi
is_v6 = utils.is_v6
is_root = utils.is_root
is_docker_user = utils.is_docker_user
is_brewblox_cwd = utils.is_brewblox_cwd
optsudo = utils.optsudo
docker_tag = utils.docker_tag
check_config = utils.check_config
sh = utils.sh
check_ok = utils.check_ok
pip_install = utils.pip_install
info = utils.info
warn = utils.warn
error = utils.error
load_ctl_lib = utils.load_ctl_lib


def show_data(data):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        if not isinstance(data, str):
            data = json.dumps(data)
        click.secho(data, fg='blue', color=opts.color)


def host_url():
    port = getenv(const.HTTPS_PORT_KEY, '443')
    return '{}:{}'.format(const.HOST, port)


def history_url():
    return '{}/history'.format(host_url())


def datastore_url():
    return '{}/datastore'.format(host_url())


def host_ip():
    try:
        # remote IP / port, local IP / port
        return getenv('SSH_CONNECTION', '').split()[2]
    except IndexError:
        return '127.0.0.1'


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())


def read_compose(fname='docker-compose.yml'):
    with open(fname) as f:
        return yaml.safe_load(f)


def write_compose(config, fname='docker-compose.yml'):  # pragma: no cover
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho('{} {}'.format(const.LOG_COMPOSE, fname), fg='magenta', color=opts.color)
        show_data(yaml.safe_dump(config))
    if not opts.dry_run:
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


def check_service_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain lowercase letters, numbers, - or _')
    return value
