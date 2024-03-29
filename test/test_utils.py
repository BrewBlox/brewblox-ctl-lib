"""
Tests brewblox_ctl_lib.utils
"""

import json
from unittest.mock import call

import click
import pytest
from brewblox_ctl_lib import utils
from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY
from configobj import ConfigObj

TESTED = utils.__name__


@pytest.fixture
def m_getenv(mocker):
    return mocker.patch(TESTED + '.getenv')


@pytest.fixture
def m_sh(mocker):
    return mocker.patch(TESTED + '.sh')


def test_show_data(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_secho = mocker.patch(TESTED + '.click.secho')

    utils.show_data('text')
    utils.show_data({'obj': True})
    assert m_secho.call_count == 2
    m_secho.assert_called_with(json.dumps({'obj': True}), fg='blue', color=m_opts.color)

    m_secho.reset_mock()
    m_opts.dry_run = False
    m_opts.verbose = False

    utils.show_data('text')
    assert m_secho.call_count == 0


def test_get_urls(m_getenv):
    m_getenv.side_effect = [
        '1234',
        '4321',
    ]
    assert utils.history_url() == f'{HOST}:1234/history/history'
    assert utils.datastore_url() == f'{HOST}:4321/history/datastore'

    assert m_getenv.call_args_list == [
        call(HTTPS_PORT_KEY, '443'),
        call(HTTPS_PORT_KEY, '443'),
    ]


def test_host_ip(m_getenv):
    m_getenv.side_effect = [
        '192.168.0.100 54321 192.168.0.69 22',
        '',
    ]
    assert utils.host_ip() == '192.168.0.69'
    assert utils.host_ip() == '127.0.0.1'


def test_user_home_exists(mocker):
    m_home = mocker.patch(TESTED + '.Path').home.return_value

    m_home.name = 'root'
    m_home.exists.return_value = False
    assert utils.user_home_exists() is False

    m_home.name = 'pi'
    m_home.exists.return_value = False
    assert utils.user_home_exists() is False

    m_home.name = 'pi'
    m_home.exists.return_value = True
    assert utils.user_home_exists() is True


def test_list_services():
    services = utils.list_services(
        'brewblox/brewblox-devcon-spark',
        'brewblox_ctl_lib/data/config/docker-compose.yml')
    assert services == ['spark-one']


def test_read_shared():
    cfg = utils.read_shared_compose(
        'brewblox_ctl_lib/data/config/docker-compose.shared.yml')
    assert 'history' in cfg['services']


@pytest.mark.parametrize('name', [
    'spark-one',
    'sparkey',
    'spark_three',
    'spark4',
])
def test_check_service_name(name):
    assert utils.check_service_name(None, 'name', name) == name


@pytest.mark.parametrize('name', [
    '',
    'spark one',
    'Sparkey',
    'spark#',
    's/park',
])
def test_check_service_name_err(name):
    with pytest.raises(click.BadParameter):
        utils.check_service_name(None, 'name', name)


def test_sh_stream(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_opts.verbose = False
    m_popen = mocker.patch(TESTED + '.subprocess.Popen')
    m_popen.return_value.stdout.readline.side_effect = [
        'line 1',
        '',
        'line 2',
        'line 3',
        ''
    ]
    m_popen.return_value.poll.side_effect = [
        None,
        0,
    ]
    assert list(utils.sh_stream('cmd')) == [
        'line 1',
        '',
        'line 2',
        'line 3',
    ]


def test_sh_stream_empty(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_opts.verbose = True
    m_popen = mocker.patch(TESTED + '.subprocess.Popen')
    m_popen.return_value.stdout.readline.side_effect = ['']
    m_popen.return_value.poll.side_effect = [0]
    assert list(utils.sh_stream('cmd')) == []


def test_pip_install(mocker, m_getenv, m_sh):
    mocker.patch(TESTED + '.Path')
    mocker.patch(TESTED + '.const.PY', '/PY')

    m_getenv.return_value = 'ussr'
    utils.pip_install('lib')
    m_sh.assert_called_with('/PY -m pip install --user --quiet --upgrade --no-cache-dir lib')

    m_getenv.return_value = None
    utils.pip_install('lib')
    m_sh.assert_called_with('sudo /PY -m pip install --quiet --upgrade --no-cache-dir lib')


def test_update_avahi_config(mocker, m_sh):
    m_info = mocker.patch(TESTED + '.info')
    m_warn = mocker.patch(TESTED + '.warn')
    m_command_exists = mocker.patch(TESTED + '.command_exists')
    mocker.patch(TESTED + '.show_data')

    config = ConfigObj()
    m_config = mocker.patch(TESTED + '.ConfigObj')
    m_config.return_value = config

    # File not found
    m_config.side_effect = OSError
    utils.update_avahi_config()
    assert m_info.call_count == 1
    assert m_warn.call_count == 1
    assert m_sh.call_count == 0

    # By default, the value is not set
    # Do not change an explicit 'no' value
    m_config.side_effect = None
    m_sh.reset_mock()
    m_warn.reset_mock()
    config['reflector'] = {'enable-reflector': 'no'}
    utils.update_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 2
    assert config['reflector']['enable-reflector'] == 'no'

    # Empty config
    m_sh.reset_mock()
    m_warn.reset_mock()
    config.clear()
    utils.update_avahi_config()
    assert m_sh.call_count == 3
    assert m_warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'yes'

    # enable-reflector already 'yes'
    m_sh.reset_mock()
    m_warn.reset_mock()
    config['reflector'] = {'enable-reflector': 'yes'}
    utils.update_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'yes'

    # Service command does not exist
    m_sh.reset_mock()
    m_warn.reset_mock()
    m_command_exists.return_value = False
    config.clear()
    utils.update_avahi_config()
    assert m_sh.call_count == 2
    assert m_warn.call_count == 1
    assert config['reflector']['enable-reflector'] == 'yes'


def test_update_system_packages(mocker, m_sh):
    m_info = mocker.patch(TESTED + '.info')
    m_command_exists = mocker.patch(TESTED + '.command_exists')

    m_command_exists.return_value = False
    utils.update_system_packages()
    assert m_sh.call_count == 0

    m_command_exists.return_value = True
    utils.update_system_packages()
    assert m_sh.call_count > 0
    assert m_info.call_count == 1


def test_add_particle_udev_rules(mocker, m_sh):
    m_info = mocker.patch(TESTED + '.info')
    m_path_exists = mocker.patch(TESTED + '.path_exists')

    m_path_exists.return_value = True
    utils.add_particle_udev_rules()
    assert m_sh.call_count == 0

    m_path_exists.return_value = False
    utils.add_particle_udev_rules()
    assert m_sh.call_count > 0
    assert m_info.call_count == 1
