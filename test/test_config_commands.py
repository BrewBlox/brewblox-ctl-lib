"""
Tests brewblox_ctl_lib.config_commands
"""

import re

import pytest

from brewblox_ctl_lib import config_commands

TESTED = config_commands.__name__


@pytest.fixture
def mocked_run(mocker):
    return mocker.patch(TESTED + '.Command.run')


@pytest.fixture
def mocked_run_all(mocker):
    return mocker.patch(TESTED + '.Command.run_all')


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.PY', '/py')


@pytest.fixture
def mocked_utils(mocker):
    mocked = [
        'check_config',
        'confirm',
        'is_pi',
        'path_exists',
        'select',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


def test_setup_command(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['path_exists'].side_effect = [
        False,  # docker-compose
        False,  # couchdb
        False,  # influxdb
        False,  # traefik
    ]
    cmd = config_commands.SetupCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    # Nothing existed, so we don't need to ask the user anything
    assert mocked_utils['confirm'].call_count == 0

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        *cmd.create_compose(),
        *cmd.update(),
        *cmd.create_datastore(),
        *cmd.create_history(),
        *cmd.create_traefik(),
        *cmd.start_config(['traefik', 'datastore', 'influx', 'history']),
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
        *cmd.set_env(),
    ]


def test_setup_partial_couch(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['path_exists'].side_effect = [
        False,  # docker-compose
        True,  # couchdb
        False,  # influxdb
        False,  # traefik
    ]
    mocked_utils['confirm'].side_effect = [
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
        *cmd.start_config(['traefik', 'datastore']),
        *cmd.config_datastore(),
        *cmd.end_config(),
        *cmd.set_env(),
    ]


def test_update(mocked_utils, mocked_run_all, mocked_py):
    cmd = config_commands.UpdateCommand()
    cmd.optsudo = 'SUDO '

    with pytest.raises(SystemExit):
        cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose down',
        'SUDO docker-compose pull',
        'sudo /py -m pip install -U brewblox-ctl',
        *cmd.lib_commands(),
        '/py -m brewblox_ctl migrate',
    ]


def test_import(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['select'].side_effect = ['dummy', 'dummy2', './out//']
    mocked_utils['path_exists'].side_effect = [
        # try 1
        False,  # couchdb,
        # try 2
        True,  # couchdb,
        False,  # influxdb,
        # try 3
        True,  # couchdb
        True,  # influxdb
    ]

    cmd = config_commands.ImportCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose up -d influx datastore traefik',
        'sleep 10',
        'curl -Sk -X GET --retry 60 --retry-delay 10 https://localhost/datastore > /dev/null',
        'export PYTHONPATH="./"; /py -m brewblox_ctl_lib.couchdb_backup import ./out/couchdb-snapshot',
        'SUDO docker cp ./out/influxdb-snapshot $(SUDO docker-compose ps -q influx):/tmp/',
        'SUDO docker-compose exec influx influxd restore -portable /tmp/influxdb-snapshot/',
    ]


def test_export(mocked_utils, mocked_run_all, mocked_py):
    mocked_utils['select'].side_effect = ['./out//']

    cmd = config_commands.ExportCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'rm -r ./out/couchdb-snapshot ./out/influxdb-snapshot || true',
        'mkdir -p ./out/couchdb-snapshot',
        'mkdir -p ./out/influxdb-snapshot',
        'SUDO docker-compose up -d influx datastore traefik',
        'sleep 10',
        'curl -Sk -X GET --retry 60 --retry-delay 10 https://localhost/datastore > /dev/null',
        'export PYTHONPATH="./"; /py -m brewblox_ctl_lib.couchdb_backup export ./out/couchdb-snapshot',
        'SUDO docker-compose exec influx rm -r /tmp/influxdb-snapshot/ || true',
        'SUDO docker-compose exec influx influxd backup -portable /tmp/influxdb-snapshot/',
        'SUDO docker cp $(SUDO docker-compose ps -q influx):/tmp/influxdb-snapshot/ ./out/'
    ]


def test_check_status(mocked_utils, mocked_run_all):
    cmd = config_commands.CheckStatusCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
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
