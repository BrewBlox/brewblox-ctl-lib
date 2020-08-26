#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rename one or more fields in Influx.

Required packages:
    - brewblox-ctl
    - click
"""
import json
import re

import click
from brewblox_ctl import utils
from brewblox_ctl.utils import sh

POLICIES = [
    'autogen',
    'downsample_1m',
    'downsample_10m',
    'downsample_1h',
    'downsample_6h',
]


def get_keys(measurement, pattern):
    retv = sh('docker-compose exec influx influx -format json ' +
              "-execute 'SHOW FIELD KEYS ON brewblox FROM brewblox.downsample_1m.\"{}\"'".format(measurement),
              capture=True)
    values = json.loads(retv)['results'][0]['series'][0]['values']
    keys = []
    for (k, t) in values:
        key = re.sub('m_', '', k, count=1)
        if re.match(pattern, key):
            keys.append(key)
    return keys


def read_fields(policy, measurement, keys):
    prefix = 'm_' * POLICIES.index(policy)
    fields = ','.join(['"{}{}"'.format(prefix, k)
                       for k in keys])

    utils.info('Reading {} {}'.format(measurement, policy))
    sh('docker-compose exec influx influx -format csv ' +
       "-execute 'SELECT {} from brewblox.{}.\"{}\"'".format(fields, policy, measurement) +
       '> /tmp/influx_rename_{}.csv'.format(policy))


def write_fields(policy, keys, pattern, replace):
    prefix = 'm_' * POLICIES.index(policy)
    fields = [re.sub(pattern, replace, k, count=1) for k in keys]
    fields = [re.sub(r' ', r'\\ ', k) for k in fields]

    infile = '/tmp/influx_rename_{}.csv'.format(policy)
    outfile = '/tmp/influx_rename_{}.line'.format(policy)
    sh('rm {}'.format(outfile), check=False)

    with open(infile) as f_in:
        if not f_in.readline():
            utils.info('No values found in policy "{}"'.format(policy))
            return

        with open(outfile, 'w') as f_out:
            f_out.write('# DML\n')
            f_out.write('# CONTEXT-DATABASE: brewblox\n')
            f_out.write('# CONTEXT-RETENTION-POLICY: {}\n'.format(policy))
            f_out.write('\n')

            while True:
                line = f_in.readline().strip()
                if not line:
                    break
                values = line.split(',')
                measurement = values.pop(0)
                time = values.pop(0)
                data = ','.join(['{}{}={}'.format(prefix, field, value)
                                 for (field, value) in zip(fields, values)
                                 if value and value != '0'])
                if data:
                    f_out.write('{} {} {}\n'.format(measurement, data, time))

    utils.info('Writing {} {}'.format(measurement, policy))
    sh('docker cp {} $(docker-compose ps -q influx):/rename'.format(outfile))
    sh('docker-compose exec influx influx -import -path=/rename || true')


@click.command()
@click.argument('measurement')
@click.argument('pattern')
@click.argument('replace')
@click.pass_context
def rename(ctx, measurement, pattern, replace):
    ctx.ensure_object(utils.ContextOpts)

    keys = get_keys(measurement, pattern)
    if not keys:
        utils.warn('No keys matching "{}" found'.format(pattern))
        return

    for policy in POLICIES:
        read_fields(policy, measurement, keys)

    for policy in POLICIES:
        write_fields(policy, keys, pattern, replace)


if __name__ == '__main__':
    rename()
