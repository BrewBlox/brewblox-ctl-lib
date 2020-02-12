"""
Tests brewblox_ctl_lib.commands.backup
"""

import json
import zipfile
from os import path
from unittest.mock import call

import pytest
import yaml

from brewblox_ctl.testing import check_sudo, invoke, matching
from brewblox_ctl_lib.commands import backup

TESTED = backup.__name__


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


def zipf_names():
    return [
        'docker-compose.yml',
        'spark-one.spark.json',
        'db1.datastore.json',
        'spark-two.spark.json',
    ]


def zipf_read():
    return [
        yaml.safe_dump({'services': {}}).encode(),
        json.dumps([{'doc1': {}}]).encode(),
        json.dumps({'blocks': []}).encode(),
        json.dumps({'blocks': [], 'other': []}).encode(),
    ]


@pytest.fixture
def m_zipf(mocker):
    m = mocker.patch(TESTED + '.zipfile.ZipFile').return_value
    m.namelist.return_value = zipf_names()
    m.read.side_effect = zipf_read()
    return m


@pytest.fixture
def f_save_backup(mocker, m_utils):
    mocker.patch(TESTED + '.http.wait')
    m_get = mocker.patch(TESTED + '.requests.get')
    m_get.return_value.text = 'resp_text'  # Used for getting Spark blocks
    m_get.return_value.json.side_effect = [
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

    m_utils.read_compose.return_value = {'services': {
        'spark-one': {
            'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
        },
        'plaato': {
            'image': 'brewblox/brewblox-plaato:rpi-edge',
        }
    }}


def test_save_backup(mocker, m_utils, f_save_backup):
    m_mkdir = mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    invoke(backup.save)

    m_mkdir.assert_called_once_with(path.abspath('backup/'))
    m_zipfile.assert_called_once_with(
        matching(r'^backup/brewblox_backup_\d{8}_\d{4}.zip'), 'w', zipfile.ZIP_DEFLATED)
    m_zipfile.return_value.write.assert_called_once_with('docker-compose.yml')
    assert m_zipfile.return_value.writestr.call_args_list == [
        call('brewblox-ui-store.datastore.json', json.dumps([{'id': 1}, {'id': 2}, {'id': 3}])),
        call('brewblox-automation.datastore.json', json.dumps([{'id': 4}, {'id': 5}, {'id': 6}])),
        call('spark-one.spark.json', 'resp_text'),
    ]


def test_save_backup_no_compose(mocker, m_zipf, m_utils, f_save_backup):
    mocker.patch(TESTED + '.mkdir')
    invoke(backup.save, '--no-save-compose')
    m_zipf.write.assert_not_called()


def test_load_backup_empty(m_utils, m_sh, m_zipf):
    m_zipf.namelist.return_value = []

    invoke(backup.load, 'fname')
    assert m_sh.call_count == 0


def test_load_backup(m_utils, m_sh, mocker, m_zipf):
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    invoke(backup.load, 'fname')
    assert m_zipf.read.call_count == 4
    assert m_tmp.call_count == 3


def test_load_backup_none(m_utils, m_sh, m_zipf):
    invoke(backup.load, 'fname --no-load-compose --no-load-datastore --no-load-spark')
    assert m_zipf.read.call_count == 0
    assert m_sh.call_count == 0


def test_load_backup_compose_missing(m_utils, m_sh, m_zipf, mocker):
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    m_zipf.namelist.return_value = zipf_names()[1:]
    m_zipf.read.side_effect = zipf_read()[1:]
    invoke(backup.load, 'fname')
    assert m_zipf.read.call_count == 3
    assert m_tmp.call_count == 3
