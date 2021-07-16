"""
Database manipulation commands
"""

import click
from brewblox_ctl import click_helpers
from brewblox_ctl_lib import migration, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def database():
    """Manual migration commands."""


@database.command()
def couchdb():
    utils.check_config()
    utils.confirm_mode()
    migration.migrate_couchdb()


@database.command()
@click.option('--target',
              default='victoria',
              help='Where to store exported data',
              type=click.Choice(['victoria', 'file']))
@click.option('--duration',
              default='',
              help='Period of exported data. Example: 30d')
@click.argument('services', nargs=-1)
def influxdb(target, duration, services):
    utils.check_config()
    utils.confirm_mode()
    migration.migrate_influxdb(target, duration, services)
