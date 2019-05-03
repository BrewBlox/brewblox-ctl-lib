"""
Collects and returns all CLI groups in the correct order
"""

from brewblox_ctl_lib import commands


def cli_sources():
    return [
        commands.cli,
    ]
