"""
Tests brewblox_ctl_lib.couchdb_backup
"""

import json
from unittest.mock import call, mock_open

import pytest

from brewblox_ctl_lib import couchdb_backup
from brewblox_ctl_lib.const import DATASTORE_URL

TESTED = couchdb_backup.__name__


def exported_data():
    return {
        'docs': [
            {
                '_id': 'dashboard-items__pretty lines',
                'rows': 5,
                'order': 1,
                'cols': 10,
                'config': {
                    'layout': {},
                    'targets': [
                        {
                            'fields': [
                                'TempSensorOneWire-2/value[degC]',
                                'TempSensorOneWire-3/value[degC]',
                                'TempSensorOneWire-4/value[degC]'
                            ],
                            'measurement': 'spark-one'
                        }
                    ],
                    'renames': {},
                    'params': {
                        'approxPoints': 100
                    }
                },
                'dashboard': 'dashboard-home',
                'feature': 'Graph'
            },
            {
                '_id': 'dashboards__dashboard-home',
                'order': 1,
                'title': 'Home Dashboard'
            },
            {
                '_id': 'services__spark-one',
                'type': 'Spark',
                'order': 1,
                'config': {},
                'title': 'Spark Controller spark-one'
            }
        ]
    }


def raw_data():
    return {
        'total_rows': 3,
        'offset': 0,
        'rows': [
            {
                'id': 'dashboard-items__pretty lines',
                'key': 'dashboard-items__pretty lines',
                'value': {
                    'rev': '8-d52a57a23432822ead776dd2781b4668'
                },
                'doc': {
                    '_id': 'dashboard-items__pretty lines',
                    '_rev': '8-d52a57a23432822ead776dd2781b4668',
                    'feature': 'Graph',
                    'dashboard': 'dashboard-home',
                    'order': 1,
                    'config': {
                        'layout': {},
                        'params': {
                            'approxPoints': 100
                        },
                        'targets': [
                            {
                                'measurement': 'spark-one',
                                'fields': [
                                    'TempSensorOneWire-2/value[degC]',
                                    'TempSensorOneWire-3/value[degC]',
                                    'TempSensorOneWire-4/value[degC]'
                                ]
                            }
                        ],
                        'renames': {}
                    },
                    'cols': 10,
                    'rows': 5
                }
            },
            {
                'id': 'dashboards__dashboard-home',
                'key': 'dashboards__dashboard-home',
                'value': {
                    'rev': '1-d4f31855b317c8afb3fe68491fc24d72'
                },
                'doc': {
                    '_id': 'dashboards__dashboard-home',
                    '_rev': '1-d4f31855b317c8afb3fe68491fc24d72',
                    'title': 'Home Dashboard',
                    'order': 1
                }
            },
            {
                'id': 'services__spark-one',
                'key': 'services__spark-one',
                'value': {
                    'rev': '1-f86a42b1e210bda1c7774de77893a36c'
                },
                'doc': {
                    '_id': 'services__spark-one',
                    '_rev': '1-f86a42b1e210bda1c7774de77893a36c',
                    'title': 'Spark Controller spark-one',
                    'order': 1,
                    'type': 'Spark',
                    'config': {}
                }
            }
        ]
    }


@pytest.fixture
def mocked_requests(mocker):
    m = mocker.patch(TESTED + '.requests')
    return m


@pytest.fixture
def mocked_glob(mocker):
    m = mocker.patch(TESTED + '.glob.glob')
    return m


@pytest.fixture
def mocked_open(mocker):
    m = mocker.patch(TESTED + '.open', mock_open(read_data=json.dumps(exported_data())))
    return m


def test_export(mocked_requests, mocked_open):
    mocked_requests.get.return_value.json.side_effect = [
        ['_system', 'mah-store'],
        raw_data(),
    ]
    couchdb_backup.export_couchdb('out')

    mocked_open.assert_called_once_with('out/mah-store.json', 'w')
    handle = mocked_open.return_value
    output = handle.write.call_args_list[0][0][0]
    assert json.loads(output) == exported_data()


def test_import(mocked_requests, mocked_glob, mocked_open):
    mocked_glob.return_value = ['out/db-one.json', 'out/db-two.json']
    couchdb_backup.import_couchdb('out')

    mocked_glob.assert_called_once_with('out/*.json')

    assert mocked_requests.put.call_args_list == [
        call('{}/{}'.format(DATASTORE_URL, 'db-one'), verify=False),
        call('{}/{}'.format(DATASTORE_URL, 'db-two'), verify=False),
    ]
    assert mocked_requests.post.call_args_list == [
        call('{}/{}/_bulk_docs'.format(DATASTORE_URL, 'db-one'), verify=False, json=exported_data()),
        call('{}/{}/_bulk_docs'.format(DATASTORE_URL, 'db-two'), verify=False, json=exported_data()),
    ]


def test_invalid_import_file(mocked_requests, mocked_glob, mocker):
    m = mock_open(read_data=json.dumps({'totallyinvalid': True}))
    mocker.patch(TESTED + '.open', m)
    mocked_glob.return_value = ['out/db-one.json', 'out/db-two.json']
    couchdb_backup.import_couchdb('out')

    assert mocked_requests.call_count == 0
