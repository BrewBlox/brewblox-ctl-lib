"""
Saving / loading backups
"""


import json
import zipfile
from contextlib import suppress
from datetime import datetime
from glob import glob
from os import getgid, getuid, mkdir, path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import click
import requests
import urllib3
import yaml
from brewblox_ctl import click_helpers, sh
from brewblox_ctl.commands import http
from brewblox_ctl_lib import const, utils
from dotenv import load_dotenv


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.group()
def backup():
    """Save or load backups."""


@backup.command()
@click.option('--save-compose/--no-save-compose',
              default=True,
              help='Include docker-compose.yml in backup.')
@click.option('--ignore-spark-error',
              is_flag=True,
              help='Skip unreachable or disconnected Spark services')
def save(save_compose, ignore_spark_error):
    """Create a backup of Brewblox settings.

    A zip archive containing JSON/YAML files is created in the ./backup/ directory.
    The archive name will include current date and time to ensure uniqueness.

    The backup is not exported to any kind of remote/cloud storage.

    To use this command in scripts, run it as `brewblox-ctl --quiet backup save`.
    Its only output to stdout will be the absolute path to the created backup.

    The command will fail if any of the Spark services could not be contacted.

    As it does not make any destructive changes to configuration,
    this command is not affected by --dry-run.

    \b
    Stored data:
    - .env
    - docker-compose.yml.   (Optional)
    - Datastore databases.
    - Spark service blocks.
    - Node-RED data.

    \b
    NOT stored:
    - History data.

    """
    utils.check_config()
    urllib3.disable_warnings()

    file = 'backup/brewblox_backup_{}.zip'.format(datetime.now().strftime('%Y%m%d_%H%M'))
    with suppress(FileExistsError):
        mkdir(path.abspath('backup/'))

    store_url = utils.datastore_url()

    utils.info('Waiting for the datastore...')
    http.wait(store_url + '/ping', info_updates=True)

    config = utils.read_compose()
    sparks = [
        k for k, v in config['services'].items()
        if v.get('image', '').startswith('brewblox/brewblox-devcon-spark')
    ]
    zipf = zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED)

    # Always save .env
    utils.info('Exporting .env')
    zipf.write('.env')

    # Always save datastore
    utils.info('Exporting datastore')
    resp = requests.post(store_url + '/mget',
                         json={'namespace': '', 'filter': '*'},
                         verify=False)
    resp.raise_for_status()
    zipf.writestr('global.redis.json', resp.text)

    if save_compose:
        utils.info('Exporting docker-compose.yml')
        zipf.write('docker-compose.yml')

    for spark in sparks:
        utils.info("Exporting Spark blocks from '{}'".format(spark))
        resp = requests.post('{}/{}/blocks/backup/save'.format(utils.host_url(), spark), verify=False)
        try:
            resp.raise_for_status()
            zipf.writestr(spark + '.spark.json', resp.text)
        except Exception as ex:
            if ignore_spark_error:
                utils.info("Skipping Spark '{}' due to error: {}".format(spark, str(ex)))
            else:
                raise ex

    for fname in [*glob('node-red/*.js*'), *glob('node-red/lib/**/*.js*')]:
        zipf.write(fname)

    zipf.close()
    click.echo(path.abspath(file))
    utils.info('Done!')


def mset(data):
    with NamedTemporaryFile('w') as tmp:
        utils.show_data(data)
        json.dump(data, tmp)
        tmp.flush()
        sh('{} http post --quiet {}/mset -f {}'.format(const.CLI,
                                                       utils.datastore_url(),
                                                       tmp.name))


@backup.command()
@click.argument('archive')
@click.option('--load-env/--no-load-env',
              default=True,
              help='Load and write .env file. Read .env values.')
@click.option('--load-compose/--no-load-compose',
              default=True,
              help='Load and write docker-compose.yml.')
@click.option('--load-datastore/--no-load-datastore',
              default=True,
              help='Load and write datastore entries.')
@click.option('--load-spark/--no-load-spark',
              default=True,
              help='Load and write Spark blocks.')
@click.option('--load-node-red/--no-load-node-red',
              default=True,
              help='Load and write Node-RED data.')
@click.option('--update/--no-update',
              default=True,
              help='Run brewblox-ctl update after loading the backup.')
def load(archive,
         load_env,
         load_compose,
         load_datastore,
         load_spark,
         load_node_red,
         update):
    """Load and apply Brewblox settings backup.

    This function uses files generated by `brewblox-ctl backup save` as input.
    You can use the --load-XXXX options to partially load the backup.

    This does not attempt to merge data: it will overwrite current docker-compose.yml,
    datastore entries, and Spark blocks.

    Blocks on Spark services not in the backup file will not be affected.

    If dry-run is enabled, it will echo all configuration from the backup archive.

    Steps:
        - Write .env
        - Read .env values
        - Write docker-compose.yml, run `docker-compose up`.
        - Write all datastore files found in backup.
        - Write all Spark blocks found in backup.
        - Write Node-RED config files found in backup.
        - Run brewblox-ctl update
    """
    utils.check_config()
    utils.confirm_mode()
    urllib3.disable_warnings()

    sudo = utils.optsudo()
    host_url = utils.host_url()
    store_url = utils.datastore_url()

    zipf = zipfile.ZipFile(archive, 'r', zipfile.ZIP_DEFLATED)
    available = zipf.namelist()
    redis_file = 'global.redis.json'
    couchdb_files = [v for v in available if v.endswith('.datastore.json')]
    spark_files = [v for v in available if v.endswith('.spark.json')]
    node_red_files = [v for v in available if v.startswith('node-red/')]

    if load_env and '.env' in available:
        utils.info('Loading .env file')
        with NamedTemporaryFile('w') as tmp:
            data = zipf.read('.env').decode()
            utils.info('Writing .env')
            utils.show_data(data)
            tmp.write(data)
            tmp.flush()
            sh('cp -f {} .env'.format(tmp.name))

        utils.info('Reading .env values')
        load_dotenv(path.abspath('.env'))

    if load_compose:
        if 'docker-compose.yml' in available:
            utils.info('Loading docker-compose.yml')
            config = yaml.safe_load(zipf.read('docker-compose.yml'))
            # Older services may still depend on the `datastore` service
            # The `depends_on` config is useless anyway in a brewblox system
            for svc in config['services'].values():
                with suppress(KeyError):
                    del svc['depends_on']
            utils.write_compose(config)
            sh('{} docker-compose up -d --remove-orphans'.format(sudo))
        else:
            utils.info('docker-compose.yml file not found in backup archive')

    if load_datastore:
        if redis_file in available or couchdb_files:
            utils.info('Waiting for the datastore...')
            sh('{} http wait {}/ping'.format(const.CLI, store_url))
            # Wipe UI/Automation, but leave Spark files
            mdelete_cmd = '{} http post {}/mdelete --quiet -d \'{{"namespace":"{}", "filter":"*"}}\''
            sh(mdelete_cmd.format(const.CLI, store_url, 'brewblox-ui-store'))
            sh(mdelete_cmd.format(const.CLI, store_url, 'brewblox-automation'))
        else:
            utils.info('No datastore files found in backup archive')

        if redis_file in available:
            data = json.loads(zipf.read(redis_file).decode())
            utils.info('Loading {} entries from Redis datastore'.format(len(data['values'])))
            mset(data)

        # Backwards compatibility for UI/automation files from CouchDB
        # The IDs here are formatted as {moduleId}__{objId}
        # The module ID becomes part of the Redis namespace
        for db in ['brewblox-ui-store', 'brewblox-automation']:
            fname = '{}.datastore.json'.format(db)
            if fname not in available:
                continue
            docs = json.loads(zipf.read(fname).decode())
            # Drop invalid names (not prefixed with module ID)
            docs[:] = [d for d in docs if len(d['_id'].split('__', 1)) == 2]
            # Add namespace / ID fields
            for d in docs:
                segments = d['_id'].split('__', 1)
                d['namespace'] = '{}:{}'.format(db, segments[0])
                d['id'] = segments[1]
                del d['_id']
            utils.info('Loading {} entries from database `{}`'.format(len(docs), db))
            mset({'values': docs})

        # Backwards compatibility for Spark service files
        # There is no module ID field here
        spark_db = 'spark-service'
        spark_fname = '{}.datastore.json'.format(spark_db)
        if spark_fname in available:
            docs = json.loads(zipf.read(spark_fname).decode())
            for d in docs:
                d['namespace'] = spark_db
                d['id'] = d['_id']
                del d['_id']
            utils.info('Loading {} entries from database `{}`'.format(len(docs), spark_db))
            mset({'values': docs})

    if load_spark:
        sudo = utils.optsudo()

        if not spark_files:
            utils.info('No Spark files found in backup archive')

        for f in spark_files:
            spark = f[:-len('.spark.json')]
            utils.info('Writing blocks to Spark service {}'.format(spark))
            with NamedTemporaryFile('w') as tmp:
                data = json.loads(zipf.read(f).decode())
                utils.show_data(data)
                json.dump(data, tmp)
                tmp.flush()
                sh('{} http post {}/{}/blocks/backup/load -f {}'.format(const.CLI, host_url, spark, tmp.name))
                sh('{} docker-compose restart {}'.format(sudo, spark))

    if load_node_red and node_red_files:
        sudo = ''
        if [getgid(), getuid()] != [1000, 1000]:
            sudo = 'sudo '

        with TemporaryDirectory() as tmpdir:
            zipf.extractall(tmpdir, members=node_red_files)
            sh('mkdir -p ./node-red')
            sh('{}chown 1000:1000 ./node-red/'.format(sudo))
            sh('{}chown -R 1000:1000 {}'.format(sudo, tmpdir))
            sh('{}cp -rfp {}/node-red/* ./node-red/'.format(sudo, tmpdir))

    zipf.close()

    if update:
        utils.info('Updating brewblox...')
        sh('{} update'.format(const.CLI))

    utils.info('Done!')
