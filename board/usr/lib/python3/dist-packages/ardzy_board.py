"""Which Ardzy board this is (Antminer S9, EBAZ4205, ...) and what it has.

The profiles are /usr/lib/ardzy/boards/<id>/board.json (the same files as boards/ in the Ardzy sources);
the board is recognised by its device tree (/proc/device-tree/compatible). Without a match: the S9.

/run/ardzy/board-io.txt (written at every boot by ardzy-board-init) tells the Ardzy libraries of every
language which Linux GPIO is which LED, button and buzzer, one per line:
    <name> <gpio> <level that means on / pressed>       for example   led_green 38 1   button_ip 51 0
"""
import json, os

BOARDS = '/usr/lib/ardzy/boards'
IO_FILE = '/run/ardzy/board-io.txt'
S9_IO = [('led_green', 38, 1), ('led_red', 37, 1), ('led_ps', 15, 0), ('buzzer', 39, 1),
         ('button_ip', 51, 0), ('button_reset', 47, 0)]
_cache = {}


def _compatible():
    try:
        return open('/proc/device-tree/compatible', 'rb').read().decode('ascii', 'replace')
    except OSError:
        return ''


def board_id():
    if 'id' not in _cache:
        comp, found = _compatible(), 's9'
        for d in (sorted(os.listdir(BOARDS)) if os.path.isdir(BOARDS) else []):
            try:
                b = json.load(open(os.path.join(BOARDS, d, 'board.json')))
            except (OSError, ValueError):
                continue
            if b.get('compatible') and b['compatible'] in comp:
                found = b['id']
                break
        _cache['id'] = found
    return _cache['id']


def profile():
    if 'profile' not in _cache:
        try:
            _cache['profile'] = json.load(open(os.path.join(BOARDS, board_id(), 'board.json')))
        except (OSError, ValueError):
            _cache['profile'] = {'id': board_id(), 'name': 'Antminer S9'}
    return _cache['profile']


def pin_control_bit():
    """The pin-control FPGA design of this board (the S9's stays where it always was)."""
    if board_id() == 's9':
        return '/usr/lib/ardzy/fpga/ardzy_io.bit'
    return os.path.join(BOARDS, board_id(), 'ardzy_io.bit')


def io_map_path(default):
    """The pin list of the pin-control design (names and places) of this board."""
    p = os.path.join(BOARDS, board_id(), 'io_map.json')
    return p if board_id() != 's9' and os.path.exists(p) else default


def board_io():
    """[(name, gpio, level that means on)] for this board's LEDs, buttons and buzzer."""
    if board_id() == 's9':
        return list(S9_IO)
    out = []
    p = profile()
    for name, led in sorted((p.get('leds') or {}).items()):
        out.append(('led_' + name, led['gpio'], 0 if led.get('active_low') else 1))
    for name, b in sorted((p.get('buttons') or {}).items()):
        out.append(('button_' + name, b['gpio'], 0 if b.get('active_low') else 1))
    if p.get('buzzer'):
        out.append(('buzzer', p['buzzer']['gpio'], 1))
    # the S9's names work too, so the same program runs on both boards
    names = [n for n, _, _ in out]
    for alias, real in (('button_ip', 's2'), ('button_reset', 's3')):
        if alias not in names and 'button_' + real in names:
            g, v = next((g, v) for n, g, v in out if n == 'button_' + real)
            out.append((alias, g, v))
    return out
