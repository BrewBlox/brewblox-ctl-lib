"""
Tests brewblox_ctl_lib.commands.update
"""

import pytest
from brewblox_ctl.testing import check_sudo, invoke

from brewblox_ctl_lib import const
from brewblox_ctl_lib.commands import update

TESTED = update.__name__


@pytest.fixture(autouse=True)
def m_path(mocker):
    m = mocker.patch(TESTED + '.Path')
    m.home.return_value.name = 'root'


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.getenv.return_value = '/usr/local/bin'
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def test_migrate(m_utils, m_sh):
    invoke(update.migrate, '--no-prune')
    m_sh.assert_called_with('{} update --no-pull --no-update-ctl --no-prune'.format(const.CLI))


def test_update(m_utils, m_sh):
    invoke(update.update, '--from-version 0.0.1', input='\n')
    invoke(update.update, '--from-version {} --no-update-ctl --prune'.format(const.CURRENT_VERSION))
    invoke(update.update, '--from-version 0.0.1 --update-ctl-done --prune')
    invoke(update.update, _err=True)
    invoke(update.update, '--from-version 0.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 9001.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 0.0.1 --no-pull --no-update-ctl --no-migrate --no-prune')
