"""
Manual migration steps
"""

from contextlib import suppress
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import List

import requests
import urllib3
from brewblox_ctl import sh

from brewblox_ctl_lib import const, utils


def migrate_compose_split():
    # Splitting compose configuration between docker-compose and docker-compose.shared.yml
    # Version pinning (0.2.2) will happen automatically
    utils.info('Moving system services to docker-compose.shared.yml...')
    config = utils.read_compose()
    sys_names = [
        'mdns',
        'eventbus',
        'influx',
        'datastore',
        'history',
        'ui',
        'traefik',
    ]
    usr_config = {
        'version': config['version'],
        'services': {key: svc for (key, svc) in config['services'].items() if key not in sys_names}
    }
    utils.write_compose(usr_config)


def migrate_compose_datastore():
    # The couchdb datastore service is gone
    # Older services may still rely on it
    utils.info('Removing `depends_on` fields from docker-compose.yml...')
    config = utils.read_compose()
    for svc in config['services'].values():
        with suppress(KeyError):
            del svc['depends_on']
    utils.write_compose(config)

    # Init dir. It will be filled during upped_migrate
    utils.info('Creating redis/ dir...')
    sh('mkdir -p redis/')


def migrate_ipv6_fix():
    # Undo disable-ipv6
    sh('sudo sed -i "/net.ipv6.*.disable_ipv6 = 1/d" /etc/sysctl.conf', check=False)

    # Enable ipv6 in docker daemon config
    utils.enable_ipv6()


def migrate_couchdb():
    urllib3.disable_warnings()
    sudo = utils.optsudo()
    opts = utils.ctx_opts()
    redis_url = utils.datastore_url()
    couch_url = 'http://localhost:5984'

    utils.info('Migrating datastore from CouchDB to Redis...')

    if opts.dry_run:
        utils.info('Dry run. Skipping migration...')
        return

    if not utils.path_exists('./couchdb/'):
        utils.info('couchdb/ dir not found. Skipping migration...')
        return

    utils.info('Starting a temporary CouchDB container on port 5984...')
    sh(f'{sudo}docker rm -f couchdb-migrate', check=False)
    sh(f'{sudo}docker run --rm -d'
        ' --name couchdb-migrate'
        ' -v "$(pwd)/couchdb/:/opt/couchdb/data/"'
        ' -p "5984:5984"'
        ' treehouses/couchdb:2.3.1')
    sh(f'{const.CLI} http wait {couch_url}')
    sh(f'{const.CLI} http wait {redis_url}/ping')

    resp = requests.get(f'{couch_url}/_all_dbs')
    resp.raise_for_status()
    dbs = resp.json()

    for db in ['brewblox-ui-store', 'brewblox-automation']:
        if db in dbs:
            resp = requests.get(f'{couch_url}/{db}/_all_docs',
                                params={'include_docs': True})
            resp.raise_for_status()
            docs = [v['doc'] for v in resp.json()['rows']]
            # Drop invalid names
            docs[:] = [d for d in docs if len(d['_id'].split('__', 1)) == 2]
            for d in docs:
                segments = d['_id'].split('__', 1)
                d['namespace'] = f'{db}:{segments[0]}'
                d['id'] = segments[1]
                del d['_rev']
                del d['_id']
            resp = requests.post(f'{redis_url}/mset',
                                 json={'values': docs},
                                 verify=False)
            resp.raise_for_status()
            utils.info(f'Migrated {len(docs)} entries from {db}')

    if 'spark-service' in dbs:
        resp = requests.get(f'{couch_url}/spark-service/_all_docs',
                            params={'include_docs': True})
        resp.raise_for_status()
        docs = [v['doc'] for v in resp.json()['rows']]
        for d in docs:
            d['namespace'] = 'spark-service'
            d['id'] = d['_id']
            del d['_rev']
            del d['_id']
        resp = requests.post(f'{redis_url}/mset',
                             json={'values': docs},
                             verify=False)
        resp.raise_for_status()
        utils.info(f'Migrated {len(docs)} entries from spark-service')

    sh(f'{sudo}docker stop couchdb-migrate')
    sh('sudo mv couchdb/ couchdb-migrated-' + datetime.now().strftime('%Y%m%d'))


def _influx_measurements() -> List[str]:
    """
    Fetch all known measurements from Influx
    This requires an InfluxDB docker container with name 'influxdb-migrate'
    to have been started.
    """
    sudo = utils.optsudo()

    raw_measurements = list(
        utils.sh_stream(
            f'{sudo}docker exec influxdb-migrate influx '
            '-database brewblox '
            "-execute 'SHOW MEASUREMENTS' "
            '-format csv'
        ))

    measurements = [
        s.strip().split(',')[1]
        for s in raw_measurements[1:]  # ignore line with headers
    ]

    return measurements


def _copy_influx_measurement(measurement: str, duration: str, target: str):
    """
    Export measurement from Influx, and copy/import to `target`.
    This requires an InfluxDB docker container with name 'influxdb-migrate'
    to have been started.
    """
    BATCH_SIZE = 10000
    sudo = utils.optsudo()
    args = f'where time > now() - {duration}' if duration else ''

    utils.info(f'Exporting history for {measurement}...')

    num_lines = 0
    offset = 0

    while True:

        generator = utils.sh_stream(
            f'{sudo}docker exec influxdb-migrate influx '
            '-database brewblox '
            f'-execute \'SELECT * FROM "brewblox"."downsample_1m"."{measurement}" {args}\' '
            f'ORDER BY time LIMIT {BATCH_SIZE} OFFSET {offset}'
            '-format csv')

        headers = next(generator, '').strip()

        if not headers:
            return

        fields = [
            f[2:].replace(' ', '\\ ')  # Remove 'm_' prefix and escape spaces
            for f in headers.split(',')[2:]  # Ignore 'name' and 'time' columns
        ]

        with NamedTemporaryFile('w') as tmp:
            for line in generator:
                if not line:
                    continue

                num_lines += 1
                values = line.strip().split(',')
                name = values[0]
                time = values[1]

                # Influx line protocol:
                # MEASUREMENT k1=1,k2=2,k3=3 TIMESTAMP
                tmp.write(f'{name} ')
                tmp.write(
                    ','.join((
                        f'{f}={v}'
                        for f, v in zip(fields, values[2:])
                        if v
                    ))
                )
                tmp.write(f' {time}\n')

            tmp.flush()

            if target == 'victoria':
                with open(tmp.name, 'rb') as rtmp:
                    url = f'{utils.host_url()}/victoria/write'
                    urllib3.disable_warnings()
                    requests.get(url, data=rtmp, verify=False)

            elif target == 'file':
                date = datetime.now().strftime('%Y%m%d_%H%M')
                fname = f'./influxdb-export/{measurement}__{date}__{duration or "all"}__{offset}.lines'
                sh(f'mkdir -p ./influxdb-export/; cp "{tmp.name}" "{fname}"')

            else:
                raise ValueError(f'Invalid target: {target}')

        offset += BATCH_SIZE
        utils.info(f'Exported {num_lines} lines')


def migrate_influxdb(target: str = 'victoria', duration: str = '', services: List[str] = []):
    """Exports InfluxDB history data.

    The exported data is either immediately imported to the new history database,
    or saved to file.
    """
    opts = utils.ctx_opts()
    sudo = utils.optsudo()

    utils.info('Exporting history data from InfluxDB...')

    if opts.dry_run:
        utils.info('Dry run. Skipping migration...')
        return

    if not utils.path_exists('./influxdb/'):
        utils.info('influxdb/ dir not found. Skipping migration...')
        return

    # Stop container in case previous migration was cancelled
    sh(f'{sudo}docker stop influxdb-migrate > /dev/null', check=False)

    # Start standalone container
    # We'll communicate using 'docker exec', so no need to publish a port
    sh(f'{sudo}docker run '
       '--rm -d '
       '--name influxdb-migrate '
       '-v "$(pwd)/influxdb:/var/lib/influxdb" '
       'influxdb:1.8 '
       '> /dev/null')

    # Do a health check until startup is done
    inner_cmd = 'curl --output /dev/null --silent --fail http://localhost:8086/health'
    bash_cmd = f'until $({inner_cmd}); do sleep 1 ; done'
    sh(f"{sudo}docker exec influxdb-migrate bash -c '{bash_cmd}'")

    # Determine relevant measurement
    # Export all of them if not specified by user
    if not services:
        services = _influx_measurements()

    utils.info(f'Exporting services: {", ".join(services)}')

    # Export data and import to target
    for svc in services:
        _copy_influx_measurement(svc, duration, target)

    # Stop migration container
    sh(f'{sudo}docker stop influxdb-migrate > /dev/null', check=False)
