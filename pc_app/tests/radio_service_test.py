"""End-to-end test of the FM radio service (fpga_projects/12_fm_radio/main.py) on a real board, through
the board's web API, the way the Ardzy app drives it: radio.json in, status.json out.
Sends only on 27.12 MHz (an ISM frequency) with no antenna, for a few seconds at a time.
Your radio settings and songs on the board are kept: radio.json is put back at the end, only the
test's own song is removed. It does not start while the radio is on air (add --force to stop it).

    python radio_service_test.py [board] [--force]          (default ardzy.local)
"""
import io
import json
import math
import os
import struct
import sys
import time
import urllib.parse
import urllib.request
import wave

FORCE = '--force' in sys.argv
_args = [a for a in sys.argv[1:] if a != '--force']
BOARD = 'http://' + (_args[0] if _args else 'ardzy.local')
P = '12_fm_radio'
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, '..', '..', 'fpga_projects', P))
results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def call(method, path, data=None, timeout=60):
    req = urllib.request.Request(BOARD + path, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def put(name, data):
    call('PUT', '/api/upload?p=%s&f=%s' % (P, urllib.parse.quote(name)), data)


def status():
    try:
        return json.loads(call('GET', '/api/file?p=%s&f=status.json' % P))
    except Exception:
        return None


def wait_status(cond, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        s = status()
        if s and cond(s):
            return s
        time.sleep(0.5)
    return status()


rev = [100]


def config(**changes):
    cfg = json.loads(call('GET', '/api/file?p=%s&f=radio.json' % P))
    for k, v in changes.items():
        if isinstance(v, dict):
            cfg.setdefault(k, {}).update(v)
        else:
            cfg[k] = v
    rev[0] += 1
    cfg['rev'] = rev[0]
    cfg['clock_checked'] = time.time()           # as the app does: the board may trust its clock
    put('radio.json', json.dumps(cfg).encode())
    return wait_status(lambda s: s.get('rev') == rev[0], 8)


# keep the user's settings; never interrupt a radio that is on air
try:
    saved = call('GET', '/api/file?p=%s&f=radio.json' % P)
except Exception:
    saved = None
try:
    live = json.loads(call('GET', '/api/file?p=%s&f=status.json' % P))
except Exception:
    live = None
if live and live.get('on') and abs(time.time() - live.get('time', 0)) < 10 and not FORCE:
    sys.exit('The radio is on air (%.3f MHz): not testing. Switch it off first, or add --force.' % live['freq_mhz'])
if saved:
    call('PUT', '/api/upload?p=%s&f=radio.json' % P, json.dumps({'on': False}).encode())

# upload the project (as the app's gallery does: settings and songs stay) and start the service
for f in ('12_fm_radio.bit', 'main.py', 'blocks.py', 'rds.py', 'modes.py', 'sstv.py', 'aes67.py', 'audio_chain.py'):
    put(f, open(os.path.join(PROJ, f), 'rb').read())
call('POST', '/api/load?p=' + P, b'', timeout=120)
s = wait_status(lambda s: True, 15)
check('service runs, writes status.json', s is not None and s['locked'], 'mode %s' % (s or {}).get('mode'))
check('starts with the transmitter off', s and s['on'] is False and s['rf_hz'] == 0)

# FM stereo with test tones and RDS on 27.12 MHz
s = config(on=True, mode='fm', freq_mhz=27.12, power=0.5, audio={'source': 'tones'},
           rds={'ps': 'TEST FM', 'rt': 'Ardzy service test {title}', 'ct': True, 'pty': 5})
check('settings applied (rev echoed)', s and s['rev'] == rev[0], s and s['error'])
time.sleep(1)
s = status()
check('FM carrier at 27.12 MHz at the pin', s and abs(s['rf_hz'] - 27.12e6) < 3000, '%s Hz' % (s or {}).get('rf_hz'))
check('level meters move (test tones)', s and s['peaks']['left'] > 0.3 and s['peaks']['mpx'] > 0.3, str((s or {}).get('peaks')))
s = wait_status(lambda s: ((s.get('rds_seen') or {}).get('ps') or '').rstrip() == 'TEST FM'
                and (s.get('rds_seen') or {}).get('rt') == 'Ardzy service test', 20)
seen = (s or {}).get('rds_seen') or {}
check('RDS seen on air: station name and text', (seen.get('ps') or '').rstrip() == 'TEST FM' and seen.get('rt') == 'Ardzy service test',
      '%r / %r, PI %s' % (seen.get('ps'), seen.get('rt'), seen.get('pi')))
s = wait_status(lambda s: (s.get('rds_seen') or {}).get('ct'), 75)
check('RDS clock time sent at the minute', bool(((s or {}).get('rds_seen') or {}).get('ct')),
      str(((s or {}).get('rds_seen') or {}).get('ct')))

# a WAV file: 3 s of 440 Hz left / 660 Hz right at 44.1 kHz
buf = io.BytesIO()
with wave.open(buf, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(44100)
    w.writeframes(b''.join(struct.pack('<hh', int(12000 * math.sin(2 * math.pi * 440 * i / 44100)),
                                       int(12000 * math.sin(2 * math.pi * 660 * i / 44100))) for i in range(44100 * 3)))
put('test_tone.wav', buf.getvalue())
s = config(audio={'source': 'playlist', 'playlist': ['test_tone.wav'], 'loop': True})
s = wait_status(lambda s: s.get('track') == 'test_tone.wav' and (s.get('track_pos_s') or 0) > 1.5, 10)
check('WAV file playing', s and s.get('track') == 'test_tone.wav', '%s at %s s' % ((s or {}).get('track'), (s or {}).get('track_pos_s')))
check('audio arrives in time (no gaps)', s and s['underruns_per_s'] == 0 and s['peaks']['left'] > 0.3,
      'underruns/s %s, peaks %s' % ((s or {}).get('underruns_per_s'), (s or {}).get('peaks')))
s = wait_status(lambda s: (s.get('rds_seen') or {}).get('rt') == 'Ardzy service test test tone', 15)
check('RDS text shows the song title', ((s or {}).get('rds_seen') or {}).get('rt') == 'Ardzy service test test tone',
      repr(((s or {}).get('rds_seen') or {}).get('rt')))
s = wait_status(lambda s: (s.get('track_pos_s') or 9) < 1.0, 6)
check('playlist loops to the start', s and (s.get('track_pos_s') or 9) < 1.0, 'position %s s' % (s or {}).get('track_pos_s'))

# Morse code: busy, then the queue empties and waits for the repeat
s = config(mode='cw', digital={'text': 'TEST', 'wpm': 30, 'repeat_s': 0, 'offset_hz': 0, 'id': 1})
s = wait_status(lambda s: s.get('digital') and s['digital']['busy'], 5)
check('CW message being sent', s and s['digital'] and s['digital']['busy'], str((s or {}).get('digital')))
s = wait_status(lambda s: s.get('digital') and not s['digital']['busy'], 10)
check('CW message finished', s and s['digital'] and not s['digital']['busy'])

# MPX capture for the app's spectrum
s = config(mode='fm', audio={'source': 'tones'}, capture=4242)
time.sleep(1.5)
m = json.loads(call('GET', '/api/file?p=%s&f=mpx.json' % P))
check('MPX capture for the spectrum', m['id'] == 4242 and len(m['samples']) == 4096)

# the new sound modes: settings applied, the carrier where it should be
for m, want in (('nfm', 27.12e6), ('usb', 27.12e6 + 1000)):
    s = config(mode=m, audio={'source': 'tones', 'tone_l': 1000, 'tone_r': 1000})
    time.sleep(1.0)
    s = status()
    check('%s: settings applied, carrier at the pin' % m.upper(), s and s['mode'] == m and abs(s['rf_hz'] - want) < 300,
          '%s Hz' % (s or {}).get('rf_hz'))

# a picture (SSTV): the test picture, Robot 36
s = config(mode='fm', audio={'source': 'sstv'}, sstv={'mode': 'robot36', 'id': 7, 'repeat_s': 0})
s = wait_status(lambda s: (s.get('picture') or {}).get('sending') and (s['picture'].get('pos_s') or 0) > 7, 15)
pic = (s or {}).get('picture') or {}
check('picture: SSTV Robot 36 being sent', pic.get('sending') and pic.get('mode') == 'Robot 36',
      '%s s of %s s, gaps %s/s' % (pic.get('pos_s'), pic.get('len_s'), (s or {}).get('underruns_per_s')))
check('picture: the sound arrives without gaps, not clipped', s and s['underruns_per_s'] == 0 and 0.4 < s['peaks']['left'] < 0.99,
      'peaks %s' % (s or {}).get('peaks'))

# AES67 from this PC: a 1 kHz tone, L24, 1 ms packets, announced with SAP
import subprocess
sender = subprocess.Popen([sys.executable, os.path.join(PROJ, 'aes67_send.py'), '--tone', '1000', '--name', 'Ardzy test',
                           '--seconds', '40'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
s = config(on=False, mode='fm', audio={'source': 'network'}, network={'stream': '', 'address': '239.69.83.67', 'port': 5004})
s = wait_status(lambda s: any(x['name'] == 'Ardzy test' for x in ((s.get('network') or {}).get('streams') or [])), 12)
streams = ((s or {}).get('network') or {}).get('streams') or []
check('AES67: the stream is found on the network (SAP)', any(x['name'] == 'Ardzy test' for x in streams),
      ', '.join('%s %s:%s' % (x['name'], x['address'], x['port']) for x in streams))
s = config(network={'stream': '239.69.83.67:5004'})
time.sleep(4)
s = status()
rv = ((s or {}).get('network') or {}).get('receiver') or {}
check('AES67: receiving, about 1000 packets per second', rv.get('receiving') and 900 < (rv.get('packets_per_s') or 0) < 1100,
      '%s packets/s, %s lost, from %s' % (rv.get('packets_per_s'), rv.get('lost'), rv.get('from')))
check('AES67: the buffer holds its 150 ms', 90 <= (rv.get('buffer_ms') or 0) <= 200, '%s ms, clock follow %s ppm' % (rv.get('buffer_ms'), rv.get('rate_adjust_ppm')))
s = config(capture=5151)
time.sleep(1.5)
m = json.loads(call('GET', '/api/file?p=%s&f=mpx.json' % P))
x = m['samples']
amp = 2 / len(x) * abs(sum(v * complex(math.cos(2 * math.pi * 1000 * i / m['fs']), -math.sin(2 * math.pi * 1000 * i / m['fs']))
                          * (0.5 - 0.5 * math.cos(2 * math.pi * i / (len(x) - 1))) for i, v in enumerate(x))) / 0.5
check('AES67: the 1 kHz tone arrives in the FPGA at its level', 0.80 * 14254 < amp < 1.15 * 14254, '%.0f (about 14254)' % amp)
# the sound chain: buffer, gain + limiter, the click counter, then the delay
s = config(network={'buffer_ms': 300}, process={'gain_db': 12, 'limiter': True, 'ceiling_db': -3, 'agc': False, 'bypass': False})
time.sleep(5)
s = status()
ch, rv = (s or {}).get('chain') or {}, ((s or {}).get('network') or {}).get('receiver') or {}
check('buffer 300 ms is kept', 230 <= (rv.get('buffer_ms') or 0) <= 380, '%s ms' % rv.get('buffer_ms'))
check('gain +12 dB, limiter at -3 dB: the tone (-6 dB) comes out at -3 dB',
      abs(max(ch.get('in_peak') or [0]) + 6) < 0.5 and abs(max(ch.get('out_peak') or [0]) + 3) < 0.3,
      'in %s dB, out %s dB, limiter %s dB' % (ch.get('in_peak'), ch.get('out_peak'), ch.get('limiter_db')))
check('no clicks: no gaps while the stream plays', s and s.get('gaps') == 0, 'gaps %s' % (s or {}).get('gaps'))
s = config(delay_s=2.0, process={'gain_db': 0, 'ceiling_db': -1})
time.sleep(4)
sender.terminate()
t_stop = time.time()
t_in = t_out = None
while time.time() - t_stop < 6 and not (t_in and t_out):
    s = status()
    ch = s.get('chain') or {}
    if t_in is None and max(ch.get('in_peak') or [0]) < -60:
        t_in = time.time() - t_stop
    if t_out is None and s['peaks']['left'] < 0.01:
        t_out = time.time() - t_stop
    time.sleep(0.1)
check('delay 2 s: the sound stops at the input at once, at the output 2 s (+ buffer) later',
      t_in is not None and t_out is not None and t_in < 1.5 and 1.7 < t_out - t_in < 3.4,   # (2 s delay + the 300 ms buffer + the FPGA's buffer, status every 0.5 s)
      'input silent after %s s, output after %s s' % (t_in and round(t_in, 2), t_out and round(t_out, 2)))
s = config(delay_s=0.0)

# RDS: a list of names, a loop of texts, PTYN, ECC, RT+
s = config(audio={'source': 'tones'}, rds={'on': True, 'ps_mode': 'list', 'ps_list': [{'text': 'ONE', 's': 1.5}, {'text': 'TWO', 's': 1.5}],
                                           'rt_list': [{'text': 'First text {freq}', 's': 4}, {'text': 'Second text', 's': 4}],
                                           'ptyn': 'Testing', 'ecc': 'E1', 'rtplus': True})
s = config(on=True, mode='fm', freq_mhz=27.12, power=0.5)
seen_ps, seen_rt, last, ptyn, ecc = set(), set(), {}, None, None
t0 = time.time()
while time.time() - t0 < 14:
    s = status()
    d = s.get('rds_seen') or {}
    for f in d.get('ps_frames') or []:
        seen_ps.add(f.strip())
    for t in (d.get('rt_frames') or []) + ([d['rt']] if d.get('rt') else []):
        seen_rt.add(t)
    last = d
    ptyn = d.get('ptyn') or ptyn
    ecc = d.get('ecc') or ecc
    time.sleep(0.5)
check('RDS: the list of names on air', {'ONE', 'TWO'} <= seen_ps, str(sorted(seen_ps)))
check('RDS: the loop of texts on air (with a variable)', {'First text 27.12', 'Second text'} <= seen_rt, str(sorted(seen_rt)))
check('RDS: PTYN and ECC on air', (ptyn or '').strip() == 'Testing' and ecc == 'E1', 'PTYN %r, ECC %r, groups %s' % (ptyn, ecc, last.get('types')))
s = config(on=False, rds={'ps_mode': 'fixed', 'rt_list': [], 'ptyn': '', 'ecc': ''})

s = config(on=False, audio={'source': 'tones'})
time.sleep(0.5)
s = status()
check('transmitter off again', s and s['on'] is False and s['rf_hz'] == 0, '%s Hz' % (s or {}).get('rf_hz'))
config(delete=['test_tone.wav'], audio={'playlist': [], 'source': 'tones'})
time.sleep(1)
if saved:                                        # the user's settings back
    put('radio.json', saved)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
