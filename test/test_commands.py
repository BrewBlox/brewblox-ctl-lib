"""
Tests brewblox_ctl_lib.commands
"""


import pytest
from click.testing import CliRunner

from brewblox_ctl_lib import commands

TESTED = commands.__name__


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


def test_ports(mocked_utils, mocked_py):
    mocked_utils.select.side_effect = [
        '1',
        '2',
        '3',
    ]

    runner = CliRunner()
    assert not runner.invoke(commands.ports).exception

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    # order is not guaranteed
    assert sorted(args) == sorted([
        '/py -m dotenv.cli --quote never set BREWBLOX_PORT_HTTP 1',
        '/py -m dotenv.cli --quote never set BREWBLOX_PORT_HTTPS 2',
        '/py -m dotenv.cli --quote never set BREWBLOX_PORT_MDNS 3',
    ])


def test_setup(mocker):
    cmd = mocker.patch(TESTED + '.setup_command')

    runner = CliRunner()
    assert not runner.invoke(commands.setup).exception
    assert cmd.action.call_count == 1


def test_update(mocked_utils, mocked_py, mocked_cli):
    mocked_utils.lib_loading_commands.return_value = ['load1', 'load2']

    runner = CliRunner()
    assert not runner.invoke(commands.update).exception

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose down',
        'SUDO docker-compose pull',
        'sudo /py -m pip install -U brewblox-ctl',
        'load1',
        'load2',
        '/cli migrate',
    ]


def test_migrate(mocker):
    cmd = mocker.patch(TESTED + '.migrate_command')

    runner = CliRunner()
    assert not runner.invoke(commands.migrate).exception
    assert cmd.action.call_count == 1


def test_status(mocked_utils):
    runner = CliRunner()
    assert not runner.invoke(commands.status).exception

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        'echo "Your release track is \\"$BREWBLOX_RELEASE\\""; ' +
        'echo "Your config version is \\"$BREWBLOX_CFG_VERSION\\""; ' +
        'SUDO docker-compose ps',
    ]


def test_log(mocker):
    cmd = mocker.patch(TESTED + '.log_command')

    runner = CliRunner()
    assert not runner.invoke(commands.log).exception
    assert cmd.action.call_count == 1
