"""
Tests brewblox_ctl_lib.commands
"""


import json
import re
import zipfile
from os import path
from unittest.mock import call

import pytest
from click.testing import CliRunner

from brewblox_ctl_lib import commands

TESTED = commands.__name__


class pytest_regex:
    """Assert that a given string meets some expectations."""

    def __init__(self, pattern, flags=0):
        self._regex = re.compile(pattern, flags)

    def __eq__(self, actual):
        return bool(self._regex.match(actual))

    def __repr__(self):
        return self._regex.pattern


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.const.PY', '/py')


@pytest.fixture
def mocked_setenv(mocker):
    return mocker.patch(TESTED + '.const.SETENV', '/dotenv')


@pytest.fixture
def mocked_cli(mocker):
    return mocker.patch(TESTED + '.const.CLI', '/cli')


@pytest.fixture
def mocked_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def mocked_lib_utils(mocker):
    m = mocker.patch(TESTED + '.lib_utils')
    return m


def test_ports(mocked_utils, mocked_setenv):
    runner = CliRunner()
    assert not runner.invoke(commands.ports, [
        '--http=1',
        '--https=2',
        '--mdns=3'
    ]).exception

    assert not runner.invoke(commands.ports, input='1\n2\n3\n').exception

    assert mocked_utils.check_config.call_count == 2
    assert mocked_utils.run_all.call_count == 2
    args = mocked_utils.run_all.call_args_list[0][0][0]
    prompted = mocked_utils.run_all.call_args_list[1][0][0]

    # order is not guaranteed in python < 3.6
    assert sorted(args) == sorted([
        '/dotenv BREWBLOX_PORT_HTTP 1',
        '/dotenv BREWBLOX_PORT_HTTPS 2',
        '/dotenv BREWBLOX_PORT_MDNS 3',
    ])
    assert sorted(prompted) == sorted(args)


def test_setup(mocker):
    cmd = mocker.patch(TESTED + '.setup_command')

    runner = CliRunner()
    assert not runner.invoke(commands.setup).exception
    assert cmd.action.call_count == 1


def test_update(mocked_utils, mocked_py, mocked_cli):
    mocked_utils.lib_loading_commands.return_value = ['load1', 'load2']

    runner = CliRunner()
    assert not runner.invoke(commands.update, input='\n').exception

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose down',
        'SUDO docker-compose pull',
        'sudo /py -m pip install -U brewblox-ctl',
        'load1',
        'load2',
        '/cli migrate --prune',
    ]


def test_migrate(mocker):
    cmd = mocker.patch(TESTED + '.migrate_command')

    runner = CliRunner()
    assert not runner.invoke(commands.migrate, ['--no-prune']).exception
    cmd.action.assert_called_once_with(False)


def test_editor(mocker, mocked_utils, mocked_lib_utils):
    mocked_utils.docker_tag.return_value = 'rpi-test'
    mocked_utils.run_all.side_effect = KeyboardInterrupt
    mocked_lib_utils.read_file.return_value = 'content'

    runner = CliRunner()
    assert not runner.invoke(commands.editor).exception

    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert mocked_utils.check_config.call_count == 1
    assert mocked_lib_utils.read_file.call_count == 2
    assert args == [
        'SUDO docker pull brewblox/brewblox-web-editor:rpi-test',
        'SUDO docker run --rm --init -p "8300:8300" -v "$(pwd):/app/config" ' +
        'brewblox/brewblox-web-editor:rpi-test --hostPort 8300'
    ]


def test_editor_changed(mocker, mocked_utils, mocked_lib_utils, mocked_cli):
    mocked_utils.docker_tag.return_value = 'rpi-test'
    mocked_lib_utils.read_file.side_effect = [
        'content',
        'changed content'
    ]

    runner = CliRunner()
    assert not runner.invoke(commands.editor).exception

    restart_args = mocked_utils.run_all.call_args_list[1][0][0]
    assert restart_args == [
        '/cli restart'
    ]


def test_discover(mocker, mocked_utils, mocked_lib_utils):
    m = mocker.patch(TESTED + '.check_call')

    runner = CliRunner()
    assert not runner.invoke(commands.discover).exception
    assert m.call_count == 2
    assert mocked_utils.run_all.call_count == 0

    assert not runner.invoke(commands.discover, ['--announce']).exception
    assert m.call_count == 2
    assert mocked_utils.run_all.call_count == 1


def test_discover_device(mocker, mocked_utils, mocked_lib_utils):
    mocked_lib_utils.subcommand.return_value = '\n'.join(['dev1', 'dev2'])
    mocked_utils.select.return_value = '2'

    assert commands._discover_device('all', 'develop', None) == 'dev2'
    assert commands._discover_device('all', 'develop', 'dev3') == 'dev2'
    assert commands._discover_device('all', 'develop', 'dev1') == 'dev1'


def test_discover_device_none(mocker, mocked_utils, mocked_lib_utils):
    mocked_lib_utils.subcommand.return_value = ''
    assert commands._discover_device('all', 'develop', None) is None


def test_add_spark(mocker, mocked_utils, mocked_lib_utils):
    devices = [
        'usb 4f0052000551353432383931 P1',
        'wifi 4f0052000551353432383931 192.168.0.71 8332'
    ]

    discovery = mocker.patch(TESTED + '._discover_device', return_value=devices[0])
    mocked_lib_utils.read_compose.return_value = {'services': {}}

    runner = CliRunner()
    assert not runner.invoke(commands.add_spark, ['-n', 'testey', '--release', 'dev']).exception

    assert mocked_lib_utils.write_compose.call_count == 1
    assert discovery.call_count == 1

    mocked_lib_utils.read_compose.return_value = {'services': {}}
    discovery.return_value = devices[1]

    assert not runner.invoke(commands.add_spark, ['-n', 'testey']).exception

    assert mocked_lib_utils.write_compose.call_count == 2
    assert discovery.call_count == 2


def test_add_spark_no_discover(mocker, mocked_utils, mocked_lib_utils):
    mocked_lib_utils.read_compose.return_value = {'services': {}}
    mocked_utils.confirm.return_value = False

    runner = CliRunner()
    assert not runner.invoke(commands.add_spark, [
        '-n', 'testey',
        '--no-discover-now',
        '--device-host=192.168.0.1',
        '--command', '"--debug"',
    ]).exception


def test_add_spark_nope(mocker, mocked_utils, mocked_lib_utils):
    discovery = mocker.patch(TESTED + '._discover_device', return_value=None)
    runner = CliRunner()

    assert runner.invoke(commands.add_spark, ['-n', '@#']).exception

    mocked_lib_utils.read_compose.return_value = {'services': {}}
    assert not runner.invoke(commands.add_spark, ['-n', 'testey']).exception

    mocked_lib_utils.read_compose.return_value = {'services': {'testey': {}}}
    assert not runner.invoke(commands.add_spark, ['-n', 'testey']).exception

    assert not runner.invoke(commands.add_spark, ['-n', 'testey', '--force']).exception

    assert mocked_lib_utils.write_compose.call_count == 0

    discovery.return_value = 'usb 4f0052000551353432383931 P1'
    assert not runner.invoke(commands.add_spark, ['-n', 'testey', '--force']).exception


def test_add_spark_id(mocker, mocked_utils, mocked_lib_utils):
    mocked_lib_utils.read_compose.return_value = {'services': {}}
    runner = CliRunner()

    assert not runner.invoke(commands.add_spark, ['-n', 'testey', '--device-id', '1234']).exception


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


def test_list_services(mocker):
    mocker.patch(TESTED + '.utils.check_config')
    runner = CliRunner()

    result = runner.invoke(commands.list_services,
                           ['--file', 'brewblox_ctl_lib/config_files/armhf/docker-compose.yml'])
    assert not result.exception
    assert result.output == 'spark-one\n'

    result = runner.invoke(
        commands.list_services,
        [
            '--image', 'brewblox/world-peace',
            '--file', 'brewblox_ctl_lib/config_files/armhf/docker-compose.yml'
        ])
    assert not result.exception
    assert result.output == ''


def test_save_backup(mocker, mocked_utils, mocked_lib_utils):
    mkdir_mock = mocker.patch(TESTED + '.mkdir')
    get_mock = mocker.patch(TESTED + '.requests.get')
    zipf_mock = mocker.patch(TESTED + '.zipfile.ZipFile')
    runner = CliRunner()

    get_mock.return_value.json.side_effect = [
        ['_system', 'brewblox-ui-store', 'brewblox-automation'],
        {'rows': [
            {'doc': {'id': 1, '_rev': 'revvy'}},
            {'doc': {'id': 2, '_rev': 'revvy'}},
            {'doc': {'id': 3, '_rev': 'revvy'}},
        ]},
        {'rows': [
            {'doc': {'id': 4, '_rev': 'revvy'}},
            {'doc': {'id': 5, '_rev': 'revvy'}},
            {'doc': {'id': 6, '_rev': 'revvy'}},
        ]},
    ]
    get_mock.return_value.text = 'resp_text'

    mocked_lib_utils.read_compose.return_value = {'services': {
        'spark-one': {
            'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
        },
        'plaato': {
            'image': 'brewblox/brewblox-plaato:rpi-edge',
        }
    }}

    result = runner.invoke(commands.save_backup)
    assert not result.exception

    mkdir_mock.assert_called_once_with(path.abspath('backup/'))
    zipf_mock.assert_called_once_with(
        pytest_regex(r'^backup/brewblox_backup_\d{8}_\d{4}.zip'), 'w', zipfile.ZIP_DEFLATED)
    assert zipf_mock.return_value.writestr.call_args_list == [
        call('brewblox-ui-store.datastore.json', json.dumps([{'id': 1}, {'id': 2}, {'id': 3}])),
        call('brewblox-automation.datastore.json', json.dumps([{'id': 4}, {'id': 5}, {'id': 6}])),
        call('spark-one.spark.json', 'resp_text'),
    ]
