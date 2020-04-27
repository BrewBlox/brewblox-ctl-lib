"""
Tests brewblox_ctl_lib.commands.spark
"""

import pytest
from brewblox_ctl.testing import check_sudo, invoke, matching

from brewblox_ctl_lib.commands import spark

TESTED = spark.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def test_discover_device(m_utils, m_sh):
    m_utils.docker_tag.return_value = 'taggy'
    assert spark.discover_device('wifi', None) == []
    m_sh.assert_called_with(
        matching(r'.* brewblox/brewblox-mdns:taggy --cli --discovery wifi'),
        capture=True)


def test_find_device(m_utils, m_sh, mocker):
    dev = '280038000847343337373738 192.168.0.55 8332'
    m_dscv = mocker.patch(TESTED + '.discover_device')
    m_dscv.return_value = [dev]

    assert spark.find_device('all', None, '192.168.0.55') == dev

    m_prompt = mocker.patch(TESTED + '.click.prompt')
    m_prompt.return_value = 1
    assert spark.find_device('all', None, None) == dev

    m_dscv.return_value = []
    assert spark.find_device('all', None, None) is None


def test_discover_spark(m_utils, m_sh, mocker):
    invoke(spark.discover_spark)
    mocker.patch(TESTED + '.discover_device').return_value = ['1', '2', '3']
    invoke(spark.discover_spark)


def test_add_spark_force(m_utils, m_sh, mocker):
    m_find = mocker.patch(TESTED + '.find_device')
    m_find.return_value = '280038000847343337373738 192.168.0.55 8332'
    m_utils.read_compose.side_effect = lambda: {'services': {'testey': {}}}

    invoke(spark.add_spark, '--name testey', _err=True)
    invoke(spark.add_spark, '--name testey --force')


def test_add_spark(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.Path')
    m_find = mocker.patch(TESTED + '.find_device')
    m_find.return_value = '280038000847343337373738 192.168.0.55 8332'
    m_utils.read_compose.side_effect = lambda: {'services': {}}

    invoke(spark.add_spark, '--name testey --discover-now --discovery wifi --command "--do-stuff"')
    invoke(spark.add_spark, input='testey\n')

    m_utils.confirm.return_value = False
    invoke(spark.add_spark, '-n testey')

    m_find.return_value = None
    invoke(spark.add_spark, '--name testey --discovery wifi', _err=True)
    invoke(spark.add_spark, '--name testey --device-host 1234')
    invoke(spark.add_spark, '--name testey --device-id 12345 --simulation')
