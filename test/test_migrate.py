"""
Tests brewblox_ctl_lib.migrate
"""

import re

import pytest

from brewblox_ctl_lib import migrate
from brewblox_ctl_lib.const import CFG_VERSION_KEY, CURRENT_VERSION

TESTED = migrate.__name__


@pytest.fixture
def mocked_getenv(mocker):
    return mocker.patch(TESTED + '.getenv')


@pytest.fixture
def mocked_run_all(mocker):
    return mocker.patch(TESTED + '.Command.run_all')


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.PY', '/py')


@pytest.fixture
def mocked_utils(mocker):
    mocked = [
        'check_config',
        'select',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


def test_migrate(mocked_getenv, mocked_run_all, mocked_py, mocked_utils):
    mocked_getenv.side_effect = ['0.0.1']
    mocked_utils['select'].side_effect = ['']

    cmd = migrate.MigrateCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        # down
        'SUDO docker-compose down',
        # downed
        'sudo rm -rf ./influxdb',
        # up
        'SUDO docker-compose up -d',
        'sleep 10',
        # upped
        'curl -Sk -X GET --retry 60 --retry-delay 10 https://localhost/history/_service/status > /dev/null',
        'curl -Sk -X POST https://localhost/history/query/configure',
        # complete
        '/py -m dotenv.cli --quote never set {} {}'.format(CFG_VERSION_KEY, CURRENT_VERSION),
    ]


def test_migrate_version_checks(mocked_getenv, mocked_run_all, mocked_utils):
    mocked_getenv.side_effect = [
        '0.0.0',
        CURRENT_VERSION,
        '9999.0.0',
    ]

    cmd = migrate.MigrateCommand()

    # 0.0.0 is not yet installed
    with pytest.raises(SystemExit):
        cmd.action()

    # current version -> noop
    cmd.action()
    assert cmd.downed_commands() == []
    assert cmd.upped_commands() == []

    # future version
    with pytest.raises(SystemExit):
        cmd.action()

    assert mocked_utils['check_config'].call_count == 3
    assert mocked_run_all.call_count == 0
