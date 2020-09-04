"""
Tests brewblox_ctl_lib.commands.backup
"""

import json
import zipfile
from os import path
from unittest.mock import call

import httpretty
import pytest
import yaml
from brewblox_ctl.testing import check_sudo, invoke, matching
from requests import HTTPError

from brewblox_ctl_lib.commands import backup

TESTED = backup.__name__
HOST_URL = 'https://localhost'
STORE_URL = HOST_URL + '/history/datastore'


@pytest.fixture(autouse=True)
def m_load_dotenv(mocker):
    m = mocker.patch(TESTED + '.load_dotenv')
    return m


@pytest.fixture
def m_utils(mocker):
    mocker.patch(TESTED + '.http.utils.info')  # Used by http.wait
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.host_url.return_value = HOST_URL
    m.datastore_url.return_value = STORE_URL
    m.info = print
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def zipf_names():
    return [
        '.env',
        'docker-compose.yml',
        'global.redis.json',
        'spark-one.spark.json',
        'brewblox-ui-store.datastore.json',
        'spark-service.datastore.json',
        'spark-two.spark.json',
    ]


def zipf_read():
    return [
        'BREWBLOX_RELEASE=9001'.encode(),
        yaml.safe_dump({
            'version': '3.7',
            'services': {
                'spark-one': {
                    'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                    'depends_on': ['datastore'],
                },
                'plaato': {
                    'image': 'brewblox/brewblox-plaato:rpi-edge',
                }
            }}).encode(),
        json.dumps({'values': []}).encode(),
        json.dumps([
            {'_id': 'module__obj', '_rev': '1234', 'k': 'v'},
            {'_id': 'invalid', '_rev': '4321', 'k': 'v'},
        ]).encode(),
        json.dumps([
            {'_id': 'spark-id', '_rev': '1234', 'k': 'v'},
        ]).encode(),
        json.dumps({'blocks': []}).encode(),
        json.dumps({'blocks': [], 'other': []}).encode(),
    ]


def redis_data():
    return {'values': [
            {'id': 'id1', 'namespace': 'n1', 'k': 'v1'},
            {'id': 'id2', 'namespace': 'n2', 'k': 'v2'},
            {'id': 'id3', 'namespace': 'n3', 'k': 'v3'},
            ]}


def blocks_data():
    return {'blocks': []}


@pytest.fixture
def m_zipf(mocker):
    m = mocker.patch(TESTED + '.zipfile.ZipFile').return_value
    m.namelist.return_value = zipf_names()
    m.read.side_effect = zipf_read()
    return m


def set_responses():
    httpretty.register_uri(
        httpretty.GET,
        STORE_URL + '/ping',
        body=json.dumps({'ping': 'pong'}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mdelete',
        body=json.dumps({'count': 1234}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mget',
        body=json.dumps(redis_data()),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mset',
        body=json.dumps(redis_data()),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-one/blocks/backup/save',
        body=json.dumps(blocks_data()),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-two/blocks/backup/save',
        body=json.dumps(blocks_data()),
        adding_headers={'ContentType': 'application/json'},
    )


@pytest.fixture
def f_read_compose(m_utils):
    m_utils.read_compose.return_value = {
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            }
        }}


@httpretty.activate(allow_net_connect=False)
def test_save_backupx(mocker, m_utils, f_read_compose):
    set_responses()
    m_mkdir = mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    invoke(backup.save)

    m_mkdir.assert_called_once_with(path.abspath('backup/'))
    m_zipfile.assert_called_once_with(
        matching(r'^backup/brewblox_backup_\d{8}_\d{4}.zip'), 'w', zipfile.ZIP_DEFLATED)
    m_zipfile.return_value.write.assert_called_with('docker-compose.yml')
    assert m_zipfile.return_value.writestr.call_args_list == [
        call('global.redis.json', json.dumps(redis_data())),
        call('spark-one.spark.json', json.dumps(blocks_data())),
    ]
    # wait, get datastore, get spark
    assert len(httpretty.latest_requests()) == 3


@httpretty.activate(allow_net_connect=False)
def test_save_backup_no_compose(mocker, m_zipf, m_utils, f_read_compose):
    set_responses()
    mocker.patch(TESTED + '.mkdir')
    invoke(backup.save, '--no-save-compose')
    m_zipf.write.assert_called_once_with('.env')


@httpretty.activate(allow_net_connect=False)
def test_save_backup_spark_err(mocker, m_zipf, m_utils, f_read_compose):
    set_responses()
    mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-one/blocks/backup/save',
        body='MEEEP',
        adding_headers={'ContentType': 'application/json'},
        status=500,
    )

    invoke(backup.save, '--no-save-compose', _err=HTTPError)

    assert m_zipfile.return_value.writestr.call_args_list == [
        call('global.redis.json', json.dumps(redis_data())),
    ]
    # wait, get datastore, get spark
    assert len(httpretty.latest_requests()) == 3


@httpretty.activate(allow_net_connect=False)
def test_save_backup_ignore_spark_err(mocker, m_zipf, m_utils, f_read_compose):
    set_responses()
    mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-one/blocks/backup/save',
        body='MEEEP',
        adding_headers={'ContentType': 'application/json'},
        status=500,
    )

    invoke(backup.save, '--no-save-compose --ignore-spark-error')

    assert m_zipfile.return_value.writestr.call_args_list == [
        call('global.redis.json', json.dumps(redis_data())),
    ]
    # wait, get datastore, get spark
    assert len(httpretty.latest_requests()) == 3


def test_load_backup_empty(m_utils, m_sh, m_zipf):
    m_zipf.namelist.return_value = []

    invoke(backup.load, 'fname')
    assert m_sh.call_count == 1  # Only the update


def test_load_backup(m_utils, m_sh, mocker, m_zipf):
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    invoke(backup.load, 'fname')
    assert m_zipf.read.call_count == 7
    assert m_tmp.call_count == 6


def test_load_backup_none(m_utils, m_sh, m_zipf):
    invoke(backup.load, 'fname --no-load-compose --no-load-datastore --no-load-spark --no-update')
    assert m_zipf.read.call_count == 1
    assert m_sh.call_count == 1


def test_load_backup_missing(m_utils, m_sh, m_zipf, mocker):
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    m_zipf.namelist.return_value = zipf_names()[2:]
    m_zipf.read.side_effect = zipf_read()[2:]
    invoke(backup.load, 'fname')
    assert m_zipf.read.call_count == 5
    assert m_tmp.call_count == 5
