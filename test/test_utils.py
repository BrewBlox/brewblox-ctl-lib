"""
Tests brewblox_ctl_lib.utils
"""

import json
from unittest.mock import call

import click
import pytest

from brewblox_ctl_lib import utils
from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY

TESTED = utils.__name__


@pytest.fixture
def m_getenv(mocker):
    return mocker.patch(TESTED + '.getenv')


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
    assert utils.get_history_url() == '{}:1234/history'.format(HOST)
    assert utils.get_datastore_url() == '{}:4321/datastore'.format(HOST)

    assert m_getenv.call_args_list == [
        call(HTTPS_PORT_KEY, '443'),
        call(HTTPS_PORT_KEY, '443'),
    ]


def test_get_host_ip(m_getenv):
    m_getenv.side_effect = [
        '192.168.0.100 54321 192.168.0.69 22',
        '',
    ]
    assert utils.get_host_ip() == '192.168.0.69'
    assert utils.get_host_ip() == '127.0.0.1'


def test_config_name(mocker):
    m_is_pi = mocker.patch(TESTED + '.is_pi')
    m_is_pi.side_effect = [True, False]
    assert utils.config_name() == 'armhf'
    assert utils.config_name() == 'amd64'


def test_list_services():
    services = utils.list_services(
        'brewblox/brewblox-devcon-spark',
        'brewblox_ctl_lib/config_files/amd64/docker-compose.yml')
    assert services == ['spark-one']


def test_read_shared():
    cfg = utils.read_shared_compose(
        'brewblox_ctl_lib/config_files/amd64/docker-compose.shared.yml')
    assert 'mdns' in cfg['services']


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
