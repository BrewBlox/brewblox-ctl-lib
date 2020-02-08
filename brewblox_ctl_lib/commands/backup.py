"""
Saving / loading backups
"""


import json
import zipfile
from contextlib import suppress
from datetime import datetime
from os import mkdir, path

import click
import requests
import urllib3

from brewblox_ctl import click_helpers
from brewblox_ctl.commands import http
from brewblox_ctl_lib import utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.group()
def backup():
    """Group: save and load backups."""


@backup.command()
def save():
    """Create a backup of Brewblox settings.

    A zip file with the output is created in the backup/ directory.
    The file name will include current date and time.

    The created file is not exported to any kind of remote/cloud storage.

    To use this command in scripts, run it as `brewblox-ctl --quiet backup save`.
    Its only output to stdout will be the absolute path to the generated file.

    The command will fail if any of the Spark services could not be contacted.

    \b
    Stored data:
    - Datastore content.
    - docker-compose.yml.
    - Blocks for all Spark services in docker-compose.yml.

    \b
    NOT stored:
    - History data.

    """
    utils.check_config()
    urllib3.disable_warnings()

    file = 'backup/brewblox_backup_{}.zip'.format(datetime.now().strftime('%Y%m%d_%H%M'))
    with suppress(FileExistsError):
        mkdir(path.abspath('backup/'))

    url = utils.get_datastore_url()
    http.wait(url, info_updates=True)
    resp = requests.get(url + '/_all_dbs', verify=False)
    resp.raise_for_status()
    dbs = [v for v in resp.json() if not v.startswith('_')]

    config = utils.read_compose()
    sparks = [
        k for k, v in config['services'].items()
        if v.get('image', '').startswith('brewblox/brewblox-devcon-spark')
    ]
    zipf = zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED)

    utils.info('Exporting databases: {}'.format(', '.join(dbs)))
    for db in dbs:
        resp = requests.get('{}/{}/_all_docs'.format(url, db),
                            params={'include_docs': True},
                            verify=False)
        resp.raise_for_status()
        docs = [v['doc'] for v in resp.json()['rows']]
        for d in docs:
            del d['_rev']
        zipf.writestr(db + '.datastore.json', json.dumps(docs))

    for spark in sparks:
        utils.info('Exporting Spark blocks from \'{}\''.format(spark))
        resp = requests.get('{}/{}/export_objects'.format(utils.base_url(), spark), verify=False)
        resp.raise_for_status()
        zipf.writestr(spark + '.spark.json', resp.text)

    zipf.close()
    click.echo(path.abspath(file))
    utils.info('Done!')
