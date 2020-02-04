"""
Collects and returns all CLI groups in the correct order
"""

from brewblox_ctl_lib.commands import backup, debug, service, setup, update


def cli_sources():
    return [
        setup.cli,
        service.cli,
        update.cli,
        debug.cli,
        backup.cli,
    ]
