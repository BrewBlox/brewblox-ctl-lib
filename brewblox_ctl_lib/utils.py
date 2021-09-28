"""
Utility functions specific to lib
"""

import json
import re
import shlex
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Generator

import click
import yaml
from brewblox_ctl import utils
from configobj import ConfigObj

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
clearenv = utils.clearenv
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
info = utils.info
warn = utils.warn
error = utils.error
load_ctl_lib = utils.load_ctl_lib
enable_ipv6 = utils.enable_ipv6


def show_data(data):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        if not isinstance(data, str):
            data = json.dumps(data)
        click.secho(data, fg='blue', color=opts.color)


def host_url():
    port = getenv(const.HTTPS_PORT_KEY, '443')
    return f'{const.HOST}:{port}'


def history_url():
    return f'{host_url()}/history/history'


def datastore_url():
    return f'{host_url()}/history/datastore'


def host_ip():
    try:
        # remote IP / port, local IP / port
        return getenv('SSH_CONNECTION', '').split()[2]
    except IndexError:
        return '127.0.0.1'


def user_home_exists() -> bool:
    home = Path.home()
    return home.name != 'root' and home.exists()


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())


def read_compose(fname='docker-compose.yml'):
    with open(fname) as f:
        return yaml.safe_load(f)


def write_compose(config, fname='docker-compose.yml'):  # pragma: no cover
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_COMPOSE} {fname}', fg='magenta', color=opts.color)
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


def sh_stream(cmd: str) -> Generator[str, None, None]:
    opts = ctx_opts()
    if opts.verbose:
        click.secho(f'{const.LOG_SHELL} {cmd}', fg='magenta', color=opts.color)

    process = subprocess.Popen(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )

    while True:
        output = process.stdout.readline()
        if not output and process.poll() is not None:
            break
        else:
            yield output


def pip_install(*libs):
    user = getenv('USER')
    args = '--quiet --upgrade --no-cache-dir ' + ' '.join(libs)
    if user and Path(f'/home/{user}').is_dir():
        return sh(f'{const.PY} -m pip install --user {args}')
    else:
        return sh(f'sudo {const.PY} -m pip install {args}')


def update_avahi_config():
    conf = const.AVAHI_CONF

    info('Checking Avahi config...')

    try:
        config = ConfigObj(conf, file_error=True)
    except OSError:
        warn(f'Avahi config file not found: {conf}')
        return

    config.setdefault('reflector', {})
    current_value = config['reflector'].get('enable-reflector')

    if current_value == 'yes':
        return

    if current_value == 'no':
        warn('Explicit "no" value found for ' +
             'reflector/enable-reflector setting in Avahi config.')
        warn('Aborting config change.')
        return

    config['reflector']['enable-reflector'] = 'yes'
    show_data(config.dict())

    with NamedTemporaryFile('w') as tmp:
        config.filename = None
        lines = config.write()
        # avahi-daemon.conf requires a 'key=value' syntax
        tmp.write('\n'.join(lines).replace(' = ', '=') + '\n')
        tmp.flush()
        sh(f'sudo chmod --reference={conf} {tmp.name}')
        sh(f'sudo cp -fp {tmp.name} {conf}')

    if command_exists('service'):
        info('Restarting avahi-daemon service...')
        sh('sudo service avahi-daemon restart')
    else:
        warn('"service" command not found. Please restart your machine to enable Wifi discovery.')


def update_system_packages():
    if command_exists('apt'):
        info('Updating apt packages...')
        sh('sudo apt -qq update && sudo apt -qq upgrade -y')


def add_particle_udev_rules():
    rules_dir = '/etc/udev/rules.d'
    target = f'{rules_dir}/50-particle.rules'
    if not path_exists(target) and command_exists('udevadm'):
        info('Adding udev rules for Particle devices...')
        sh(f'sudo mkdir -p {rules_dir}')
        sh(f'sudo cp {const.CONFIG_DIR}/50-particle.rules {target}')
        sh('sudo udevadm control --reload-rules && sudo udevadm trigger')
