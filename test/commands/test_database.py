"""
Tests brewblox_ctl_lib.commands.database
"""

import pytest
from brewblox_ctl.testing import invoke
from brewblox_ctl_lib.commands import database

TESTED = database.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    return m


@pytest.fixture
def m_migration(mocker):
    m = mocker.patch(TESTED + '.migration')
    return m


def test_couchdb(m_utils, m_migration):
    invoke(database.couchdb)
    m_utils.check_config.assert_called_once()
    m_utils.confirm_mode.assert_called_once()
    m_migration.migrate_couchdb.assert_called_once()


def test_influxdb(m_utils, m_migration):
    invoke(database.influxdb, '--duration=1d s1 s2')
    m_utils.check_config.assert_called_once()
    m_utils.confirm_mode.assert_called_once()
    m_migration.migrate_influxdb.assert_called_once_with('victoria', '1d', ['s1', 's2'])