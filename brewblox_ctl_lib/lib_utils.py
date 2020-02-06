"""
Utility functions specific to lib
"""

import re

import click
import yaml

from brewblox_ctl.utils import ctx_opts, getenv, is_pi
from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY, LOG_COMPOSE


def is_dry():
    ctx = click.get_current_context()
    return ctx.ensure_object(dict).get('dry', False)


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
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho('{} {}'.format(LOG_COMPOSE, fname), fg='magenta', color=opts.color)

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


def get_host_url():
    try:
        # remote IP / port, local IP / port
        return getenv('SSH_CONNECTION', '').split()[2]
    except IndexError:
        return '127.0.0.1'
