"""
Device discovery
"""

import re
from glob import glob
from queue import Empty, Queue
from socket import inet_ntoa

import click
from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

from brewblox_ctl_lib import utils

BREWBLOX_DNS_TYPE = '_brewblox._tcp.local.'
DISCOVER_TIMEOUT_S = 5


def discover_usb():
    lines = '\n'.join([f for f in glob('/dev/serial/by-id/*')])
    for obj in re.finditer(r'particle_(?P<model>p1|photon)_(?P<serial>[a-z0-9]+)-',
                           lines,
                           re.IGNORECASE | re.MULTILINE):
        id = obj.group('serial')
        model = obj.group('model')
        # 'usb ' is same length as 'wifi'
        desc = 'usb  {} {}'.format(id, model)
        yield {
            'id': id,
            'desc': desc,
            'model': model,
        }


def discover_wifi():
    queue = Queue()
    conf = Zeroconf()

    def on_service_state_change(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            queue.put(info)

    try:
        ServiceBrowser(conf, BREWBLOX_DNS_TYPE, handlers=[on_service_state_change])
        while True:
            info = queue.get(timeout=DISCOVER_TIMEOUT_S)
            if not info or not info.addresses or info.addresses == [b'\x00\x00\x00\x00']:
                continue  # discard simulators
            id = info.server[:-len('.local.')]
            host = inet_ntoa(info.addresses[0])
            port = info.port
            desc = 'wifi {} {} {}'.format(id, host, port)
            yield {
                'id': id,
                'desc': desc,
                'host': host,
                'port': port,
            }
    except Empty:
        pass
    finally:
        conf.close()


def discover_device(discovery_type):
    utils.info('Discovering devices...')
    if discovery_type in ['all', 'usb']:
        yield from discover_usb()
    if discovery_type in ['all', 'wifi']:
        yield from discover_wifi()


def find_device(discovery_type, device_host=None):
    devs = []

    for i, dev in enumerate(discover_device(discovery_type)):
        if not device_host:
            devs.append(dev)
            click.echo('device {} :: {}'.format(i+1, dev['desc']))

        # Don't echo discarded devices
        if device_host and dev.get('host') == device_host:
            click.echo('{} matches --device-host {}'.format(dev['desc'], device_host))
            return dev

    if device_host or not devs:
        click.echo('No devices discovered')
        return None

    idx = click.prompt('Which device do you want to use?',
                       type=click.IntRange(1, len(devs)),
                       default=1)

    return devs[idx-1]
