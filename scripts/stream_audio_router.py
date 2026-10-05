"""Route only the real Dota process to OBS, with local headset monitoring.

Requires pactl. Does not change the default output or route other applications.
Stop with Ctrl+C to restore the original output and release owned modules.
"""
from pathlib import Path
import json
import signal
import subprocess
import time

BUS = 'jutsu_dota_stream'


def pactl(*args):
    return subprocess.check_output(
        ['pactl', *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def items(kind):
    return json.loads(pactl('-f', 'json', 'list', kind))


def is_dota(stream, clients):
    # PulseAudio client identifiers may be strings, even when indices are ints.
    props = clients.get(str(stream.get('client')), {})
    if props.get('application.process.binary') != 'dota2':
        return False
    try:
        pid = int(props['application.process.id'])
        if pid <= 0:
            return False
        return Path('/proc', str(pid), 'exe').resolve(strict=True).name == 'dota2'
    except (OSError, TypeError, ValueError, KeyError):
        return False


def main():
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    owned, original = [], {}
    headset = pactl('get-default-sink')
    if headset == BUS:
        raise SystemExit('El monitor debe ser una salida física.')
    try:
        if not any(s['name'] == BUS for s in items('sinks')):
            owned.append(pactl(
                'load-module', 'module-null-sink', 'sink_name=' + BUS,
                'sink_properties=device.description=Jutsu-Dota-Stream',
                'rate=48000', 'channels=2',
            ))
        if not any(
            m['name'] == 'module-loopback'
            and ('source=' + BUS + '.monitor') in m.get('argument', '')
            for m in items('modules')
        ):
            owned.append(pactl(
                'load-module', 'module-loopback', 'source=' + BUS + '.monitor',
                'sink=' + headset, 'latency_msec=10',
                'source_dont_move=true', 'sink_dont_move=true',
            ))
        while running:
            clients = {str(c['index']): c.get('properties', {}) for c in items('clients')}
            sinks = {s['index']: s['name'] for s in items('sinks')}
            for stream in items('sink-inputs'):
                if is_dota(stream, clients) and sinks.get(stream['sink']) != BUS:
                    original.setdefault(stream['index'], sinks.get(stream['sink'], headset))
                    pactl('move-sink-input', str(stream['index']), BUS)
            time.sleep(2)
    finally:
        try:
            clients = {str(c['index']): c.get('properties', {}) for c in items('clients')}
            for stream in items('sink-inputs'):
                if stream['index'] in original and is_dota(stream, clients):
                    try:
                        pactl('move-sink-input', str(stream['index']), original[stream['index']])
                    except subprocess.CalledProcessError:
                        pass
        finally:
            for module in reversed(owned):
                try:
                    pactl('unload-module', module)
                except subprocess.CalledProcessError:
                    pass


if __name__ == '__main__':
    main()
