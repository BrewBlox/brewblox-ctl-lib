"""
Tests brewblox_ctl_lib.migrate
"""

import re

import pytest

from brewblox_ctl_lib import migrate_command
from brewblox_ctl_lib.const import CFG_VERSION_KEY, CURRENT_VERSION

TESTED = migrate_command.__name__


@pytest.fixture
def mocked_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def mocked_lib_utils(mocker):
    m = mocker.patch(TESTED + '.lib_utils')
    m.get_history_url.return_value = 'HISTORY'
    m.get_datastore_url.return_value = 'DATASTORE'
    return m


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.const.PY', '/py')


@pytest.fixture
def mocked_cli(mocker):
    return mocker.patch(TESTED + '.const.CLI', '/cli')


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


def test_migrate(mocked_py, mocked_cli, mocked_utils, mocked_lib_utils):
    mocked_utils.getenv.side_effect = ['0.0.1']
    mocked_utils.select.side_effect = ['']
    mocked_lib_utils.read_compose.return_value = {
        'services': {
            'datastore': {},
            'traefik': {},
            'influx': {},
        }
    }

    migrate_command.action()

    assert mocked_utils.check_config.call_count == 1
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        # down
        'SUDO docker-compose down --remove-orphans',
        # downed
        'sudo rm -rf ./influxdb',
        # up
        'SUDO docker-compose up -d',
        # upped
        '/cli http wait HISTORY/ping',
        '/cli http post HISTORY/query/configure',
        '/cli http wait DATASTORE',
        '/cli http put DATASTORE/_users',
        '/cli http put DATASTORE/_replicator',
        '/cli http put DATASTORE/_global_changes',
        # complete
        '/py -m dotenv.cli --quote never set {} {}'.format(CFG_VERSION_KEY, CURRENT_VERSION),
    ]

    mocked_lib_utils.write_compose.assert_called_once_with({
        'services': {
            'datastore': {'image': 'treehouses/couchdb:2.3.1'},
            'traefik': {'image': 'traefik:v1.7'},
            'influx': {'image': 'influxdb:1.7'},
        }
    })


def test_migrate_version_checks(mocked_cli, mocked_utils, mocked_lib_utils):
    mocked_utils.getenv.side_effect = [
        '0.0.0',
        CURRENT_VERSION,
        '9999.0.0',
        '9999.0.0',
    ]
    mocked_utils.confirm.side_effect = [
        False,  # abort on newer version
        True,  # continue on newer version
    ]

    # 0.0.0 is not yet installed
    with pytest.raises(SystemExit):
        migrate_command.action()

    # current version
    migrate_command.action()
    assert migrate_command.downed_commands(CURRENT_VERSION) == []
    assert migrate_command.upped_commands(CURRENT_VERSION) == [
        '/cli http wait HISTORY/ping',
        '/cli http post HISTORY/query/configure',
        '/cli http wait DATASTORE',
        '/cli http put DATASTORE/_users',
        '/cli http put DATASTORE/_replicator',
        '/cli http put DATASTORE/_global_changes',
    ]
    assert mocked_utils.run_all.call_count == 1

    # future version, and abort confirm
    with pytest.raises(SystemExit):
        migrate_command.action()

    assert mocked_utils.check_config.call_count == 3
    assert mocked_utils.run_all.call_count == 1

    # future version, continue anyway
    migrate_command.action()
