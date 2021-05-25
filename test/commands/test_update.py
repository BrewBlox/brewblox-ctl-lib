"""
Tests brewblox_ctl_lib.commands.update
"""

import json

import httpretty
import pytest
from brewblox_ctl.testing import check_sudo, invoke
from brewblox_ctl_lib import const
from brewblox_ctl_lib.commands import update

TESTED = update.__name__

STORE_URL = 'https://localhost/history/datastore'


@pytest.fixture(autouse=True)
def m_path(mocker):
    m = mocker.patch(TESTED + '.Path')
    m.home.return_value.name = 'root'


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.getenv.return_value = '/usr/local/bin'
    m.datastore_url.return_value = STORE_URL
    m.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'depends_on': ['datastore'],
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
            'automation': {
                'image': 'brewblox/brewblox-automation:${BREWBLOX_RELEASE}',
            }
        }}
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def test_migrate(m_utils, m_sh):
    invoke(update.migrate, '--no-prune')
    m_sh.assert_called_with('{} update --no-pull --no-update-ctl --no-prune'.format(const.CLI))


def test_libs(m_utils, m_sh):
    invoke(update.libs)
    m_utils.load_ctl_lib.assert_called_once_with()
    m_sh.assert_not_called()


def test_update(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.datastore_migrate_redis')

    invoke(update.update, '--from-version 0.0.1', input='\n')
    invoke(update.update, '--from-version {} --no-update-ctl --prune'.format(const.CURRENT_VERSION))
    invoke(update.update, '--from-version 0.0.1 --update-ctl-done --prune')
    invoke(update.update, _err=True)
    invoke(update.update, '--from-version 0.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 9001.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 0.0.1 --no-pull --no-update-ctl --no-migrate --no-prune --no-avahi-config')

    m_utils.getenv.return_value = None
    invoke(update.update, '--from-version {} --no-update-ctl --prune'.format(const.CURRENT_VERSION))


def test_datastore_migrate_noop(m_utils, m_sh):
    m_utils.ctx_opts.return_value.dry_run = True
    update.datastore_migrate_redis()
    m_sh.assert_not_called()

    m_utils.ctx_opts.return_value.dry_run = False
    m_utils.path_exists.return_value = False
    update.datastore_migrate_redis()
    m_sh.assert_not_called()


@httpretty.activate(allow_net_connect=False)
def test_datastore_migrate_redis_empty(m_utils, m_sh, mocker):
    m_utils.ctx_opts.return_value.dry_run = False
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/_all_dbs',
        body=json.dumps(['unused']),  # no known databases found -> nothing migrated
        adding_headers={'ContentType': 'application/json'},
    )
    update.datastore_migrate_redis()
    assert len(httpretty.latest_requests()) == 1


@httpretty.activate(allow_net_connect=False)
def test_datastore_migrate_redis(m_utils, m_sh, mocker):
    m_utils.ctx_opts.return_value.dry_run = False
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/_all_dbs',
        body=json.dumps(['brewblox-ui-store', 'spark-service']),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/brewblox-ui-store/_all_docs',
        body=json.dumps({'rows': [
            {'doc': {'_id': 'module__obj', '_rev': '1234', 'k': 'v'}},
            {'doc': {'_id': 'invalid', '_rev': '1234', 'k': 'v'}},
        ]}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/spark-service/_all_docs',
        body=json.dumps({'rows': [
            {'doc': {'_id': 'spaced__id', '_rev': '1234', 'k': 'v'}},
            {'doc': {'_id': 'valid', '_rev': '1234', 'k': 'v'}},
        ]}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mset',
        body='{"values":[]}',
        adding_headers={'ContentType': 'application/json'},
    )

    update.datastore_migrate_redis()
    assert len(httpretty.latest_requests()) == 5


def test_check_automation_ui(m_utils):
    update.check_automation_ui()
    assert 'automation-ui' in m_utils.write_compose.call_args[0][0]['services']

    m_utils.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {}
    }

    # No automation service -> no changes
    update.check_automation_ui()
    assert m_utils.write_compose.call_count == 1
