"""
Collects and returns all CLI groups in the correct order
"""

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
