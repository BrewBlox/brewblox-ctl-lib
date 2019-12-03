"""
Tests brewblox_ctl_lib.log_command
"""

import re

import pytest

from brewblox_ctl_lib import log_command

TESTED = log_command.__name__


@pytest.fixture
def mocked_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture(autouse=True)
def mocked_lib_utils(mocker):
    m = mocker.patch(TESTED + '.lib_utils')
    m.read_compose.return_value = {
        'services': {
            'spark-one': {},
        }
    }
    m.read_shared_compose.return_value = {
        'services': {
            'history': {},
            'ui': {},
        }
    }
    return m


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


def test_log_file(mocked_utils):
    mocked_utils.select.side_effect = ['my reason']
    mocked_utils.confirm.side_effect = [
        True,  # include compose
        True,  # view log
        True,  # export log
    ]

    log_command.action()

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 2
    args = mocked_utils.run_all.call_args_list[0][0][0]
    share_args = mocked_utils.run_all.call_args_list[1][0][0]

    assert args == [
        *log_command.add_header('my reason'),
        *log_command.add_vars(),
        *log_command.add_logs(),
        *log_command.add_compose(),
        *log_command.add_blocks(),
        *log_command.add_inspect(),
    ]

    assert share_args == [
        'cat brewblox.log | nc termbin.com 9999'
    ]

    check_optsudo(args)


def test_log_file_nopes(mocked_utils):
    mocked_utils.select.side_effect = ['my reason']
    mocked_utils.confirm.side_effect = [
        False,  # include compose
        False,  # view log
        False,  # export log
    ]

    log_command.action()

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    assert mocked_utils.run.call_count == 0
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        *log_command.add_header('my reason'),
        *log_command.add_vars(),
        *log_command.add_logs(),
        *log_command.add_blocks(),
        *log_command.add_inspect(),
    ]


def test_add_log_error(mocked_utils, mocked_lib_utils):
    mocked_lib_utils.read_compose.side_effect = RuntimeError('whoops')
    assert 'whoops' in log_command.add_logs()[1]
