"""
Collects and returns all CLI groups in the correct order
"""

try:
    from brewblox_ctl_lib import const, utils  # noqa: F401
except AttributeError as ex:  # pragma: no cover
    CTL_VERSION = '0.24.4'  # can't be placed in const
    print('Failed to import dependency from brewblox-ctl.')
    print('The minimum required version is {}.'.format(CTL_VERSION))
    print('To update brewblox-ctl, run: \n\n\t python3 -m pip install --user --upgrade --no-cache-dir brewblox-ctl \n')
    raise ex

from brewblox_ctl_lib.commands import (add_device, backup, diagnostic, service,
                                       setup, update)


def cli_sources():
    return [
        setup.cli,
        add_device.cli,
        service.cli,
        update.cli,
        diagnostic.cli,
        backup.cli,
    ]
