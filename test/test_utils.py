"""
Tests brewblox_ctl_lib.lib_utils
"""

from unittest.mock import call

import pytest

from brewblox_ctl_lib import lib_utils
from brewblox_ctl_lib.const import HOST, HTTPS_PORT_KEY

TESTED = lib_utils.__name__


@pytest.fixture
def mocked_ext(mocker):
    mocked = [
        'getenv',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def test_get_urls(mocked_ext):
    mocked_ext['getenv'].side_effect = [
        '1234',
        '4321',
    ]
    assert lib_utils.get_history_url() == '{}:1234/history'.format(HOST)
    assert lib_utils.get_datastore_url() == '{}:4321/datastore'.format(HOST)

    assert mocked_ext['getenv'].call_args_list == [
        call(HTTPS_PORT_KEY, '443'),
        call(HTTPS_PORT_KEY, '443'),
    ]


def test_list_services():
    services = lib_utils.list_services(
        'brewblox/brewblox-devcon-spark',
        'brewblox_ctl_lib/config_files/docker-compose_amd64.yml')
    assert services == ['spark-one']
