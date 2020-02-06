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

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.commands import http
from brewblox_ctl_lib import lib_utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.group()
def backup():
    """Commands for creating and loading backups"""


@backup.command()
def save():
    """Export datastore files and Spark blocks to zip file"""
    utils.check_config()
    urllib3.disable_warnings()

    file = 'backup/brewblox_backup_{}.zip'.format(datetime.now().strftime('%Y%m%d_%H%M'))
    with suppress(FileExistsError):
        mkdir(path.abspath('backup/'))

    url = lib_utils.get_datastore_url()
    http.wait(url)
    resp = requests.get(url + '/_all_dbs', verify=False)
    resp.raise_for_status()
    dbs = [v for v in resp.json() if not v.startswith('_')]

    config = lib_utils.read_compose()
    sparks = [
        k for k, v in config['services'].items()
        if v.get('image', '').startswith('brewblox/brewblox-devcon-spark')
    ]
    zipf = zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED)

    utils.info('Exporting databases:', ', '.join(dbs))
    for db in dbs:
        resp = requests.get('{}/{}/_all_docs'.format(url, db),
                            params={'include_docs': True},
                            verify=False)
        resp.raise_for_status()
        docs = [v['doc'] for v in resp.json()['rows']]
        for d in docs:
            del d['_rev']
        zipf.writestr(db + '.datastore.json', json.dumps(docs))

    utils.info('Exporting Spark blocks:', ', '.join(sparks))
    for spark in sparks:
        resp = requests.get('{}/{}/export_objects'.format(lib_utils.base_url(), spark), verify=False)
        resp.raise_for_status()
        zipf.writestr(spark + '.spark.json', resp.text)

    zipf.close()
    utils.info('Created', path.abspath(file))
