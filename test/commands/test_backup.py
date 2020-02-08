"""
Tests brewblox_ctl_lib.commands.backup
"""

import json
import zipfile
from os import path
from unittest.mock import call

import pytest

from brewblox_ctl.testing import invoke, matching
from brewblox_ctl_lib.commands import backup

TESTED = backup.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


def test_save_backup(mocker, m_utils):
    mocker.patch(TESTED + '.http.wait')
    mkdir_mock = mocker.patch(TESTED + '.mkdir')
    get_mock = mocker.patch(TESTED + '.requests.get')
    zipf_mock = mocker.patch(TESTED + '.zipfile.ZipFile')

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

    m_utils.read_compose.return_value = {'services': {
        'spark-one': {
            'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
        },
        'plaato': {
            'image': 'brewblox/brewblox-plaato:rpi-edge',
        }
    }}

    invoke(backup.save)

    mkdir_mock.assert_called_once_with(path.abspath('backup/'))
    zipf_mock.assert_called_once_with(
        matching(r'^backup/brewblox_backup_\d{8}_\d{4}.zip'), 'w', zipfile.ZIP_DEFLATED)
    assert zipf_mock.return_value.writestr.call_args_list == [
        call('brewblox-ui-store.datastore.json', json.dumps([{'id': 1}, {'id': 2}, {'id': 3}])),
        call('brewblox-automation.datastore.json', json.dumps([{'id': 4}, {'id': 5}, {'id': 6}])),
        call('spark-one.spark.json', 'resp_text'),
    ]
