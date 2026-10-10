"""The boards Ardzy knows: boards/<id>/board.json (chip, memory, LEDs, buttons, pins, how it boots).

Shared by the app (FPGA builds, views, the SD card maker) and copied onto every board image
(/usr/lib/ardzy/boards), where the Ardzy tools pick the profile of the board they run on.
"""
import json, os, sys

DEFAULT = 's9'


def boards_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(getattr(sys, '_MEIPASS', here), 'boards'), os.path.join(here, '..', 'boards'),
              os.path.join(here, 'boards')):
        if os.path.isfile(os.path.join(d, DEFAULT, 'board.json')):
            return os.path.normpath(d)
    raise RuntimeError('the board profiles (boards/) are missing')


def ids():
    d = boards_dir()
    found = [n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, 'board.json'))]
    return sorted(found, key=lambda n: (n != DEFAULT, n))         # the S9 first


def load(board_id=None):
    board_id = board_id or DEFAULT
    p = os.path.join(boards_dir(), board_id, 'board.json')
    if not os.path.isfile(p):
        raise ValueError('unknown board "%s" (known: %s)' % (board_id, ', '.join(ids())))
    b = json.load(open(p, encoding='utf-8'))
    b['dir'] = os.path.dirname(p)
    return b


def all_boards():
    return [load(i) for i in ids()]


def from_model(model='', compatible=''):
    """The board id for what a board reports (its device-tree model / compatible string)."""
    text = (model + ' ' + compatible).lower()
    for b in all_boards():
        if b.get('compatible', '\0') in text or b['name'].lower() in text:
            return b['id']
    return DEFAULT if 'antminer' in text or not text.strip() else None
