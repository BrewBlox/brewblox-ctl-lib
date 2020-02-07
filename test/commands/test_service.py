"""
Tests brewblox_ctl_lib.commands.service
"""

import pytest

from brewblox_ctl.testing import check_sudo, invoke
from brewblox_ctl_lib import const
from brewblox_ctl_lib.commands import service

TESTED = service.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.read_compose.return_value = {
        'services': {
            'spark-one': {},
        }
    }
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def test_show(m_utils, m_sh):
    m_utils.list_services.return_value = ['s1', 's2']
    invoke(service.show, '--image brewblox --file docker-compose.shared.yml')
    m_utils.list_services.assert_called_once_with('brewblox', 'docker-compose.shared.yml')


def test_remove(m_utils, m_sh):
    invoke(service.remove, '-n spark-one')
    invoke(service.remove, '-n spark-none')
    invoke(service.remove, _err=True)


def test_editor(m_utils, m_sh):
    invoke(service.editor)
    assert m_utils.confirm.call_count == 0

    m_utils.read_file.side_effect = [
        {
            'services': {
                'spark-one': {},
            }
        },
        {
            'services': {
                'spark-one': {'edited': True},
            }
        },
    ]
    invoke(service.editor)
    assert m_utils.confirm.call_count == 1
    m_sh.assert_any_call('{} restart'.format(const.CLI))
