"""
Tests brewblox_ctl_lib.config_commands
"""

import re
from unittest.mock import call

import pytest

from brewblox_ctl_lib import config_commands

TESTED = config_commands.__name__


@pytest.fixture
def mocked_run(mocker):
    return mocker.patch(TESTED + '.Command.run')


@pytest.fixture
def mocked_announce(mocker):
    return mocker.patch(TESTED + '.Command.announce')


@pytest.fixture
def mocked_run_all(mocker):
    return mocker.patch(TESTED + '.Command.run_all')


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.PY', '/py')


@pytest.fixture
def mocked_cli(mocker):
    return mocker.patch(TESTED + '.CLI', '/cli')


@pytest.fixture
def mocked_utils(mocker):
    mocked = [
        'check_config',
        'check_output',
        'confirm',
        'is_pi',
        'path_exists',
        'select',
        'getenv',
        'get_history_url',
        'get_datastore_url',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


def test_ports(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['select'].side_effect = [
        '1',
        '2',
        '3',
    ]

    cmd = config_commands.PortsCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    # order is not guaranteed
    assert sorted(args) == sorted([
        '/py -m dotenv.cli --quote never set BREWBLOX_PORT_HTTP 1',
        '/py -m dotenv.cli --quote never set BREWBLOX_PORT_HTTPS 2',
        '/py -m dotenv.cli --quote never set BREWBLOX_PORT_MDNS 3',
    ])


def test_setup_command(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['path_exists'].side_effect = [
        False,  # docker-compose
        False,  # couchdb
        False,  # influxdb
        False,  # traefik
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # no port check
        True,  # update ctl
    ]
    cmd = config_commands.SetupCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    # Nothing existed, so we only asked the user about ports and ctl
    assert mocked_utils['confirm'].call_count == 2

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        *cmd.create_compose(),
        *cmd.update(),
        *cmd.update_ctl(),
        *cmd.create_datastore(),
        *cmd.create_history(),
        *cmd.create_traefik(),
        *cmd.start_config(['traefik', 'influx', 'history', 'datastore']),
        *cmd.config_datastore(),
        *cmd.config_history(),
        *cmd.end_config(),
        *cmd.set_env(),
    ]

    check_optsudo(args)


def test_setup_no_config(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['path_exists'].side_effect = [
        True,  # docker-compose
        True,  # couchdb
        True,  # influxdb
        True,  # traefik
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # no port check
        False,  # no ctl update
        True,  # keep compose
        True,  # keep couchdb
        True,  # keep influxdb
        True,  # keep traefik
    ]
    cmd = config_commands.SetupCommand()
    cmd.action()

    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        *cmd.update(),
        *cmd.start_config(['traefik', 'influx', 'history']),
        *cmd.config_history(),
        *cmd.end_config(),
        *cmd.set_env(),
    ]


def test_setup_check_ports_ok(mocked_utils, mocked_run_all, mocked_announce):
    mocked_utils['getenv'].side_effect = [
        '1',
        '2',
        '3',
    ]
    mocked_utils['confirm'].side_effect = [
        True,  # yes, check
    ]
    mocked_utils['path_exists'].side_effect = [
        True,  # compose exists
    ]
    mocked_utils['check_output'].return_value = ''

    cmd = config_commands.SetupCommand()
    cmd.optsudo = 'SUDO '
    cmd.check_ports()

    assert mocked_run_all.call_count == 1
    assert mocked_run_all.call_args_list == [
        call(['SUDO docker-compose down --remove-orphans'])
    ]

    port_commands = [
        'sudo netstat -tulpn | grep ":1[[:space:]]" || true',
        'sudo netstat -tulpn | grep ":2[[:space:]]" || true',
        'sudo netstat -tulpn | grep ":3[[:space:]]" || true',
    ]

    assert mocked_announce.call_args_list == [call(port_commands)]
    assert mocked_utils['check_output'].call_args_list == [
        call(cmd, shell=True) for cmd in port_commands
    ]


def test_setup_check_ports_nok(mocked_utils, mocked_run_all, mocked_announce):
    mocked_utils['getenv'].side_effect = [
        '1',
        '2',
        '3',
    ]
    mocked_utils['confirm'].side_effect = [
        True,  # yes, check
        True,  # continue
        False,  # exit
    ]
    mocked_utils['path_exists'].side_effect = [
        False,  # no compose
    ]
    mocked_utils['check_output'].side_effect = [
        '',
        'used',
        'used',
    ]

    cmd = config_commands.SetupCommand()
    cmd.optsudo = 'SUDO '
    with pytest.raises(SystemExit):
        cmd.check_ports()

    assert mocked_run_all.call_count == 0  # no need to compose down
    assert mocked_announce.call_count == 1
    assert mocked_utils['check_output'].call_count == 3


def test_setup_partial_couch(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['path_exists'].side_effect = [
        False,  # docker-compose
        True,  # couchdb
        False,  # influxdb
        False,  # traefik
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # no port check
        False,  # no ctl update
        True,  # keep couchdb
    ]
    cmd = config_commands.SetupCommand()
    cmd.action()

    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        *cmd.create_compose(),
        *cmd.update(),
        *cmd.create_history(),
        *cmd.create_traefik(),
        *cmd.start_config(['traefik', 'influx', 'history']),
        *cmd.config_history(),
        *cmd.end_config(),
        *cmd.set_env(),
    ]


def test_setup_partial_influx(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['path_exists'].side_effect = [
        False,  # docker-compose
        False,  # couchdb
        True,  # influxdb
        False,  # traefik
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # no port check
        False,  # no ctl update
        True,  # keep influx
    ]
    cmd = config_commands.SetupCommand()
    cmd.action()

    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        *cmd.create_compose(),
        *cmd.update(),
        *cmd.create_datastore(),
        *cmd.create_traefik(),
        *cmd.start_config(['traefik', 'influx', 'history', 'datastore']),
        *cmd.config_datastore(),
        *cmd.config_history(),
        *cmd.end_config(),
        *cmd.set_env(),
    ]


def test_update(mocked_utils, mocked_run_all, mocked_py):
    cmd = config_commands.UpdateCommand()
    cmd.optsudo = 'SUDO '

    with pytest.raises(SystemExit):
        cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_utils['confirm'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose down',
        'SUDO docker-compose pull',
        'sudo /py -m pip install -U brewblox-ctl',
        *cmd.lib_commands(),
        '/py -m brewblox_ctl flash',
        '/py -m brewblox_ctl migrate',
    ]


def test_update_no_flash(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['confirm'].return_value = False
    cmd = config_commands.UpdateCommand()
    cmd.optsudo = 'SUDO '

    with pytest.raises(SystemExit):
        cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_utils['confirm'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose down',
        'SUDO docker-compose pull',
        'sudo /py -m pip install -U brewblox-ctl',
        *cmd.lib_commands(),
        '/py -m brewblox_ctl migrate',
    ]


def test_import(mocked_utils, mocked_run_all, mocked_py, mocked_cli):
    mocked_utils['select'].side_effect = ['./out//']
    mocked_utils['get_datastore_url'].side_effect = [
        '/datastore'
    ]

    cmd = config_commands.ImportCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose up -d datastore traefik',
        '/cli http wait /datastore',
        'export PYTHONPATH="./"; /py -m brewblox_ctl_lib.couchdb_backup import ./out',
    ]


def test_export(mocked_utils, mocked_run_all, mocked_py, mocked_cli):
    mocked_utils['select'].side_effect = ['./out//']
    mocked_utils['get_datastore_url'].side_effect = [
        '/datastore'
    ]

    cmd = config_commands.ExportCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'mkdir -p ./out',
        'SUDO docker-compose up -d datastore traefik',
        '/cli http wait /datastore',
        'export PYTHONPATH="./"; /py -m brewblox_ctl_lib.couchdb_backup export ./out',
    ]


def test_check_status(mocked_utils, mocked_run_all):
    cmd = config_commands.CheckStatusCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'echo "Your release track is \\"$BREWBLOX_RELEASE\\""; ' +
        'echo "Your config version is \\"$BREWBLOX_CFG_VERSION\\""; ' +
        'SUDO docker-compose ps',
    ]


def test_log_file(mocked_utils, mocked_run_all, mocked_run):
    mocked_utils['select'].side_effect = ['my reason']
    mocked_utils['confirm'].side_effect = [
        True,  # include compose
        True,  # view log
        True,  # export log
    ]

    cmd = config_commands.LogFileCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 2
    assert mocked_run.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]
    share_args = mocked_run_all.call_args_list[1][0][0]

    assert args == [
        *cmd.add_header('my reason'),
        *cmd.add_vars(),
        *cmd.add_compose(),
        *cmd.add_logs(),
        *cmd.add_inspect(),
    ]

    assert share_args == [
        'cat brewblox.log | nc termbin.com 9999'
    ]

    check_optsudo(args)


def test_log_file_nopes(mocked_utils, mocked_run_all, mocked_run):
    mocked_utils['select'].side_effect = ['my reason']
    mocked_utils['confirm'].side_effect = [
        False,  # include compose
        False,  # view log
        False,  # export log
    ]

    cmd = config_commands.LogFileCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    assert mocked_run.call_count == 0
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        *cmd.add_header('my reason'),
        *cmd.add_vars(),
        *cmd.add_logs(),
        *cmd.add_inspect(),
    ]
