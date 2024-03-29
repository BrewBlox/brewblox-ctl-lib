"""
Tests brewblox_ctl_lib.commands.update
"""

from distutils.version import StrictVersion

import pytest
from brewblox_ctl.testing import check_sudo, invoke
from brewblox_ctl_lib import const
from brewblox_ctl_lib.commands import update

TESTED = update.__name__

STORE_URL = 'https://localhost/history/datastore'


class DummyError(Exception):
    pass


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.getenv.return_value = '/usr/local/bin:/home/pi/.local/bin'
    m.datastore_url.return_value = STORE_URL
    m.user_home_exists.return_value = False  # Tested explicitly
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


def test_libs(m_utils, m_sh):
    invoke(update.libs)
    m_utils.load_ctl_lib.assert_called_once_with()
    m_sh.assert_not_called()


def test_update(m_utils, m_sh, mocker):
    # mocker.patch(TESTED + '.migration')

    invoke(update.update, '--from-version 0.0.1', input='\n')
    invoke(update.update, f'--from-version {const.CURRENT_VERSION} --no-update-ctl --prune')
    invoke(update.update, '--from-version 0.0.1 --update-ctl-done --prune')
    invoke(update.update, _err=True)
    invoke(update.update, '--from-version 0.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 9001.0.0 --prune', _err=True)
    invoke(update.update,
           '--from-version 0.0.1 --no-pull --no-update-ctl' +
           ' --no-migrate --no-prune --no-update-system')

    m_utils.getenv.return_value = None
    invoke(update.update, f'--from-version {const.CURRENT_VERSION} --no-update-ctl --prune')


def test_check_version(m_utils, mocker):
    mocker.patch(TESTED + '.const.CURRENT_VERSION', '1.2.3')
    mocker.patch(TESTED + '.SystemExit', DummyError)

    update.check_version(StrictVersion('1.2.2'))

    with pytest.raises(DummyError):
        update.check_version(StrictVersion('0.0.0'))

    with pytest.raises(DummyError):
        update.check_version(StrictVersion('1.3.0'))


# def test_check_path(m_utils, m_sh, mocker):
#     mocker.patch(TESTED + '.SystemExit', DummyError)

#     m_utils.user_home_exists.return_value = False
#     m_utils.getenv.return_value = '/usr/bin'
#     update.check_path()
#     assert m_sh.call_count == 0

#     m_utils.user_home_exists.return_value = True
#     m_utils.getenv.return_value = '/usr/bin:/home/$USER/.local/bin'
#     update.check_path()
#     assert m_sh.call_count == 0

#     m_utils.user_home_exists.return_value = True
#     m_utils.getenv.return_value = '/usr/bin'
#     with pytest.raises(DummyError):
#         update.check_path()
#     assert m_sh.call_count > 0


# def test_check_automation_ui(m_utils):
#     update.check_automation_ui()
#     assert 'automation-ui' in m_utils.write_compose.call_args[0][0]['services']

#     m_utils.read_compose.side_effect = lambda: {
#         'version': '3.7',
#         'services': {}
#     }

#     # No automation service -> no changes
#     update.check_automation_ui()
#     assert m_utils.write_compose.call_count == 1
