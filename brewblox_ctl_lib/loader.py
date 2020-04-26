"""
Collects and returns all CLI groups in the correct order
"""

try:
    from brewblox_ctl_lib import const, utils  # noqa: F401
except AttributeError as ex:  # pragma: no cover
    CTL_VERSION = '0.21.0'  # can't be placed in const
    print('Failed to import dependency from brewblox-ctl.')
    print('The minimum required version is {}.'.format(CTL_VERSION))
    print('To update brewblox-ctl, run: \n\n\t pip3 install --user --upgrade --no-cache-dir brewblox-ctl \n')
    raise ex

from brewblox_ctl_lib.commands import (backup, diagnostic, service, setup,
                                       spark, update)


def cli_sources():
    return [
        setup.cli,
        spark.cli,
        service.cli,
        update.cli,
        diagnostic.cli,
        backup.cli,
    ]
