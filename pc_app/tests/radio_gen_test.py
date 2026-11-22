"""The radio's new modes on a real board, through the board's web API the way the Ardzy app drives them:
a picture in the waterfall (I/Q and USB), radiofax, APRS, DTMF, Hellschreiber, PSK63, QRSS and WSPR.
It uploads project 12_fm_radio (the .bit and the programs), then sends each mode for a few seconds on
27.12 MHz (an ISM frequency) with no antenna, low power. Your radio.json is put back at the end; the
pictures it sends are removed again. It does not start while the radio is on air (--force stops it).

    python radio_gen_test.py [board] [--force]          (default ardzy.local)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

FORCE = '--force' in sys.argv
_args = [a for a in sys.argv[1:] if a != '--force']
BOARD = 'http://' + (_args[0] if _args else 'ardzy.local')
P = '12_fm_radio'
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, '..', '..', 'fpga_projects', P))
sys.path.insert(0, PROJ)
import paint  # noqa: E402

results = []
q = urllib.parse.quote


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('%-4s %-56s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def call(method, path, data=None, timeout=60):
    req = urllib.request.Request(BOARD + path, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def put(name, data):
    call('PUT', '/api/upload?p=%s&f=%s' % (P, q(name)), data)


def status():
    try:
        return json.loads(call('GET', '/api/file?p=%s&f=status.json' % P))
    except Exception:
        return None


def wait(cond, timeout=10.0):
    t = time.time()
    s = None
    while time.time() - t < timeout:
        s = status()
        if s and cond(s):
            return s
        time.sleep(0.4)
    return s


rev = [int(time.time()) % 100000 * 10]


def send(cfg):
    rev[0] += 1
    cfg = dict(cfg, rev=rev[0], clock_checked=time.time())
    put('radio.json', json.dumps(cfg).encode())
    return wait(lambda s: s.get('rev') == rev[0], 10)


# ---------------------------------------------------------------- the user's settings, then upload
try:
    saved = call('GET', '/api/file?p=%s&f=radio.json' % P)
    user = json.loads(saved)
except Exception:
    saved, user = None, {}
s0 = status()
if s0 and time.time() - s0.get('time', 0) < 6 and s0.get('on') and not FORCE:
    print('The radio is on air now: not testing (add --force to stop it for the test).')
    sys.exit(1)
info = json.loads(call('GET', '/api/info'))
was = info.get('current')
SKIP = ('guide.md', 'guide.html', 'pins.xdc', 'top.v', 'selftest.py', 'project.json')
for f in sorted(os.listdir(PROJ)):
    path = os.path.join(PROJ, f)
    if os.path.isfile(path) and f not in SKIP and not f.startswith('make_') and (f == P + '.bit' or f.endswith('.py')):
        put(f, open(path, 'rb').read())
t = time.time()
r = json.loads(call('POST', '/api/load?p=' + P, b''))
s = wait(lambda s: time.time() - s.get('time', 0) < 3 and 'has_iq' in s, 30)
check('radio service runs the new programs', s is not None and 'has_iq' in s, 'up in %.1f s' % (time.time() - t))
check('the design has the I/Q mode', s and s.get('has_iq') is True)

base = json.loads(json.dumps(s['config'])) if s else {}
base.update(on=False, freq_mhz=27.12, power=0.3)
base['audio'] = dict(base.get('audio', {}), source='tones')
put('radio.json', json.dumps(dict(base, rev=0)).encode())
time.sleep(1)

# ---------------------------------------------------------------- a picture in the waterfall
img = paint.test_picture(120, 80)
tmp = os.path.join(HERE, '_wf.pgm')
paint.write_pgm(tmp, img)
put('paint_image.pgm', open(tmp, 'rb').read())
os.remove(tmp)
pc = dict(base['paint'], kind='iq', width_hz=20000, offset_hz=0, line_ms=25, repeat_s=0, id=1)
t0 = time.time()
s = send(dict(base, on=True, mode='paint', paint=pc))
s = wait(lambda s: (s.get('generated') or {}).get('sending'), 20)
g = (s or {}).get('generated') or {}
check('paint I/Q: prepared and sending', g.get('sending') and g.get('hw') == 'iq' and g.get('have_image'),
      '%s, ready %.1f s after the settings' % (g.get('what'), time.time() - t0))
time.sleep(1.2)
s = status()
check('paint I/Q: no gaps in the samples (FIFO kept full)', s and s['underruns_per_s'] == 0 and not s['error'],
      'underruns %s/s, FIFO %s, error "%s"' % (s.get('underruns_per_s'), s.get('audio_fifo'), s.get('error')))
inf = g.get('info') or {}
check('paint I/Q: 120 columns over 20 kHz, 80 lines of 25 ms', inf.get('columns') == 120 and inf.get('lines') == 80 and
      19500 < inf.get('width_hz', 0) <= 20000 and abs(inf.get('seconds', 0) - 2.0) < 0.01, str(inf))
s = wait(lambda s: not (s.get('generated') or {}).get('sending'), 8)
check('paint I/Q: ends after the picture (once)', s and not s['generated']['sending'] and s['generated']['next_in_s'] is None,
      'after %.1f s' % (time.time() - t0))
s = send(dict(base, on=True, mode='paint', paint=dict(pc, kind='usb', width_hz=2400, line_ms=20, id=2)))
s = wait(lambda s: (s.get('generated') or {}).get('sending'), 15)
g = (s or {}).get('generated') or {}
check('paint USB: sending through the side-band filter', g.get('sending') and g.get('hw') == 'usb', str(g.get('what')))
s = send(dict(base, on=True, mode='paint', paint=dict(pc, line_ms=10, repeat_s=1, id=3)))
s = wait(lambda s: (s.get('generated') or {}).get('next_in_s') is not None, 15)
check('paint: repeats when asked', s and s['generated']['next_in_s'] is not None)

# ---------------------------------------------------------------- radiofax
put('fax_image.pgm', b'P5\n100 20\n255\n' + bytes(range(100)) * 20)
s = send(dict(base, on=True, mode='wefax', wefax=dict(base['wefax'], phasing_s=0, lpm=240, id=1)))
s = wait(lambda s: (s.get('generated') or {}).get('sending'), 10)
g = (s or {}).get('generated') or {}
check('WEFAX: sending in USB', g.get('sending') and g.get('hw') == 'usb', '%s, %s s' % (g.get('what'), g.get('len_s')))
time.sleep(2)
s = status()
check('WEFAX: no gaps', s and s['underruns_per_s'] == 0 and not s['error'], 'underruns %s/s' % s.get('underruns_per_s'))
s = send(dict(base, on=True, mode='wefax', wefax=dict(base['wefax'], phasing_s=0, lpm=240, via='fm', id=2)))
s = wait(lambda s: (s.get('generated') or {}).get('hw') == 'fm', 10)
check('WEFAX: or in NFM', s and s['generated']['hw'] == 'fm')

# ---------------------------------------------------------------- APRS, DTMF
s = send(dict(base, on=True, mode='aprs', packet=dict(base['packet'], call='N0CALL-7', repeat_s=2, id=1)))
s = wait(lambda s: (s.get('generated') or {}).get('next_in_s') is not None, 10)
g = (s or {}).get('generated') or {}
check('APRS: one packet sent, the next one waits', g.get('next_in_s') is not None and 'N0CALL-7>APZARD,WIDE1-1' in g.get('what', ''),
      '%s, %.2f s' % (g.get('what'), g.get('len_s', 0)))
check('APRS: NFM, deviation measured', g.get('hw') == 'fm' and not s['error'], 'peak %s kHz' % s.get('deviation_khz'))
s = send(dict(base, on=True, mode='dtmf', dtmf=dict(base['dtmf'], digits='0123456789*#', id=1)))
s = wait(lambda s: (s.get('generated') or {}).get('sending'), 10)
check('DTMF: sending 12 keys', s and s['generated']['sending'] and abs(s['generated']['len_s'] - 2.5) < 0.2,
      '%s s' % (s and s['generated']['len_s']))

# ---------------------------------------------------------------- symbol modes
for mode, extra, want_s in (('hell', {'text': 'CQ ARDZY'}, 8.0), ('psk63', {'text': 'test'}, 2.4), ('qrss', {'text': 'E', 'qrss_dot_s': 1}, 8.0)):
    d = dict(base['digital'], repeat_s=0, offset_hz=0, **extra)
    s = send(dict(base, on=True, mode=mode, digital=d))
    s = wait(lambda s: (s.get('digital') or {}).get('busy'), 6)
    dg = (s or {}).get('digital') or {}
    check('%s: sending, %.1f s long' % (mode.upper(), dg.get('length_s', 0)), dg.get('busy') and abs(dg.get('length_s', 0) - want_s) < 0.6
          and not s['error'], 'error "%s"' % (s or {}).get('error'))
d = dict(base['digital'], wspr_call='K1ABC', wspr_locator='KM17', wspr_dbm=10, wspr_every_min=10, offset_hz=1500)
s = send(dict(base, on=True, mode='wspr', digital=d))
s = wait(lambda s: (s.get('digital') or {}).get('total'), 6)
dg = (s or {}).get('digital') or {}
now = time.time()
check('WSPR: waits for the next even minute + 1 s', dg.get('busy') is False and dg.get('next_in_s') is not None and
      dg['next_in_s'] <= 121 and abs((now + dg['next_in_s']) % 120 - 1) < 1.5,
      'starts in %s s, %s symbols, %s s' % (dg.get('next_in_s'), dg.get('total'), dg.get('length_s')))
s = send(dict(base, on=True, mode='wspr', digital=dict(d, wspr_locator='ZZ99')))
check('WSPR: a bad locator is refused with a reason', s and 'locator' in (s.get('error') or ''), (s or {}).get('error'))

# ---------------------------------------------------------------- a sound mode still works after them
s = send(dict(base, on=True, mode='fm', power=1.0))    # (full power: the edge counter sees every period)
time.sleep(1.0)
s = status()
check('FM after the new modes: carrier at 27.12 MHz again', s and abs(s['rf_hz'] - 27.12e6) < 150e3 and not s.get('generated'),
      '%s Hz' % (s and s['rf_hz']))

# ---------------------------------------------------------------- back as it was
# (never /api/delete: it removes the whole project. The service deletes the test pictures itself.)
user['rev'] = rev[0] + 1
put('radio.json', json.dumps(dict(user, delete=['paint_image.pgm', 'fax_image.pgm']), indent=1).encode())
s = wait(lambda s: s.get('rev') == rev[0] + 1, 10)
time.sleep(1)
put('radio.json', saved if saved is not None else json.dumps(user, indent=1).encode())   # your file exactly
left = json.loads(call('GET', '/api/status'))
files = next((x['files'] for x in left['projects'] if x['name'] == P), [])
check('your radio.json is back (transmitter %s), test pictures gone' % ('on' if user.get('on') else 'off'),
      s and s.get('on') == bool(user.get('on')) and not any(f.endswith('.pgm') for f in files), ', '.join(files))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
