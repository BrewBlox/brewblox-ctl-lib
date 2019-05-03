"""
Tests brewblox_ctl_.setup_command
"""


import re
from unittest.mock import call

import pytest

from brewblox_ctl_lib import setup_command

TESTED = setup_command.__name__


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.const.PY', '/py')


@pytest.fixture
def mocked_cli(mocker):
    return mocker.patch(TESTED + '.const.CLI', '/cli')


@pytest.fixture
def mocked_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


def test_setup_command(mocked_utils, mocked_py):
    mocked_utils.path_exists.side_effect = [
        False,  # docker-compose
        False,  # couchdb
        False,  # influxdb
        False,  # traefik
    ]
    mocked_utils.confirm.side_effect = [
        False,  # no port check
        True,  # update ctl
    ]
    setup_command.action()

    # Nothing existed, so we only asked the user about ports and ctl
    assert mocked_utils.confirm.call_count == 2

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        *setup_command.create_compose(),
        *setup_command.update(),
        *setup_command.update_ctl(),
        *setup_command.create_datastore(),
        *setup_command.create_history(),
        *setup_command.create_traefik(),
        *setup_command.start_config(['traefik', 'influx', 'history', 'datastore']),
        *setup_command.config_datastore(),
        *setup_command.config_history(),
        *setup_command.end_config(),
        *setup_command.set_env(),
    ]

    check_optsudo(args)


def test_setup_no_config(mocked_utils, mocked_py):
    mocked_utils.path_exists.side_effect = [
        True,  # docker-compose
        True,  # couchdb
        True,  # influxdb
        True,  # traefik
    ]
    mocked_utils.confirm.side_effect = [
        False,  # no port check
        False,  # no ctl update
        True,  # keep compose
        True,  # keep couchdb
        True,  # keep influxdb
        True,  # keep traefik
    ]

    setup_command.action()

    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        *setup_command.update(),
        *setup_command.start_config(['traefik', 'influx', 'history']),
        *setup_command.config_history(),
        *setup_command.end_config(),
        *setup_command.set_env(),
    ]


def test_setup_check_ports_ok(mocked_utils):
    mocked_utils.getenv.side_effect = [
        '1',
        '2',
        '3',
    ]
    mocked_utils.confirm.side_effect = [
        True,  # yes, check
    ]
    mocked_utils.path_exists.side_effect = [
        True,  # compose exists
    ]
    mocked_utils.check_output.return_value = ''

    setup_command.check_ports()

    assert mocked_utils.run_all.call_count == 1
    assert mocked_utils.run_all.call_args_list == [
        call(['SUDO docker-compose down --remove-orphans'])
    ]

    port_commands = [
        'sudo netstat -tulpn | grep ":1[[:space:]]" || true',
        'sudo netstat -tulpn | grep ":2[[:space:]]" || true',
        'sudo netstat -tulpn | grep ":3[[:space:]]" || true',
    ]

    assert mocked_utils.announce.call_args_list == [call(port_commands)]
    assert mocked_utils.check_output.call_args_list == [
        call(setup_command, shell=True) for setup_command in port_commands
    ]


def test_setup_check_ports_nok(mocked_utils):
    mocked_utils.getenv.side_effect = [
        '1',
        '2',
        '3',
    ]
    mocked_utils.confirm.side_effect = [
        True,  # yes, check
        True,  # continue
        False,  # exit
    ]
    mocked_utils.path_exists.side_effect = [
        False,  # no compose
    ]
    mocked_utils.check_output.side_effect = [
        '',
        'used',
        'used',
    ]

    with pytest.raises(SystemExit):
        setup_command.check_ports()

    assert mocked_utils.run_all.call_count == 0  # no need to compose down
    assert mocked_utils.announce.call_count == 1
    assert mocked_utils.check_output.call_count == 3


def test_setup_partial_couch(mocked_utils, mocked_py):
    mocked_utils.path_exists.side_effect = [
        False,  # docker-compose
        True,  # couchdb
        False,  # influxdb
        False,  # traefik
    ]
    mocked_utils.confirm.side_effect = [
        False,  # no port check
        False,  # no ctl update
        True,  # keep couchdb
    ]
    setup_command.action()

    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        *setup_command.create_compose(),
        *setup_command.update(),
        *setup_command.create_history(),
        *setup_command.create_traefik(),
        *setup_command.start_config(['traefik', 'influx', 'history']),
        *setup_command.config_history(),
        *setup_command.end_config(),
        *setup_command.set_env(),
    ]


def test_setup_partial_influx(mocked_utils, mocked_py):
    mocked_utils.path_exists.side_effect = [
        False,  # docker-compose
        False,  # couchdb
        True,  # influxdb
        False,  # traefik
    ]
    mocked_utils.confirm.side_effect = [
        False,  # no port check
        False,  # no ctl update
        True,  # keep influx
    ]
    setup_command.action()

    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        *setup_command.create_compose(),
        *setup_command.update(),
        *setup_command.create_datastore(),
        *setup_command.create_traefik(),
        *setup_command.start_config(['traefik', 'influx', 'history', 'datastore']),
        *setup_command.config_datastore(),
        *setup_command.config_history(),
        *setup_command.end_config(),
        *setup_command.set_env(),
    ]
