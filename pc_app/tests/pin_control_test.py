"""Full test of the pin-control FPGA design on a real board, through the board's web API.

Drives only j4[0], j4[1] (PWM) and j1[1] (UART loopback: TX and RX on the same pin); every pin is
an input again at the end.

    python pin_control_test.py [host]
"""
import json, sys, time, urllib.parse, urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else 'ardzy.local'
results = []


def call(method, path):
    req = urllib.request.Request('http://%s%s' % (HOST, path), method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def P(path, **q):
    return call('POST', path + ('?' + urllib.parse.urlencode(q) if q else ''))


def G(path):
    return call('GET', path)


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def la_capture(rate, trig=''):
    P('/api/la/start', rate=rate, pre=10, trig=trig)
    for _ in range(60):
        time.sleep(0.05)
        if G('/api/la')['done']:
            break
    return G('/api/la/data')


io = G('/api/io')
if 'pins' not in io:                    # not loaded (another design ran last): load it, like the app does
    print('loading the pin-control design (project ardzy_io) ...', flush=True)
    P('/api/load', p='ardzy_io')
    time.sleep(1)
    io = G('/api/io')
check('pin-control design answers', io.get('version') == 2, 'version %s, %d pins' % (io.get('version'), len(io['pins'])))

# 1. logic analyzer: every channel against the live pin levels (nothing driven)
lv = [p['level'] for p in io['pins']]
d = la_capture(1000000)
lv2 = [p['level'] for p in G('/api/io')['pins']]
bad = set()
for k, lo, hi in d['changes']:
    v = lo | hi << 32
    for i, (a, b) in enumerate(zip(lv, lv2)):
        if a == b and (v >> i & 1) != a:
            bad.add(d['signals'][i])
check('logic analyzer: all 49 pin channels', not bad, 'mismatch: ' + ', '.join(sorted(bad)) if bad else '')

# 2. PWM + frequency meters
P('/api/io/pwm/set', ch=0, hz=1000, duty=25, pin='j4[0]')
P('/api/io/pwm/set', ch=1, hz=10000000, duty=50, pin='j4[1]')
P('/api/io/meas/set', ch=0, signal='j4[0]', gate_s=1)
P('/api/io/meas/set', ch=1, signal='j4[1]')
time.sleep(2.3)
m = G('/api/io/meas')['channels']
check('PWM 1 kHz 25 % measured', abs(m[0]['hz'] - 1000) < 0.5 and abs(m[0]['duty_pct'] - 25) < 0.5,
      '%.3f Hz, %.2f %%' % (m[0]['hz'], m[0]['duty_pct']))
check('PWM 10 MHz 50 % measured', abs(m[1]['hz'] - 1e7) < 10 and abs(m[1]['duty_pct'] - 50) < 2,
      '%.1f Hz, %.2f %%' % (m[1]['hz'], m[1]['duty_pct']))

# 3. logic analyzer: trigger on the PWM, period 1000 samples at 1 MHz
d = la_capture(1000000, trig='j4[0]:rise')
i0 = d['signals'].index('j4[0]')
edges, last = [], None
for idx, lo, hi in d['changes']:
    v = ((hi << 32 | lo) >> i0) & 1
    if last == 0 and v == 1:
        edges.append(idx)
    last = v
periods = [b - a for a, b in zip(edges, edges[1:])]
check('logic analyzer trigger + PWM period', bool(periods) and all(p == 1000 for p in periods) and d['trigger_at'] in edges,
      'periods %s, trigger at %d' % (periods[:4], d['trigger_at']))

# 4. UART loopback
for baud, data in ((115200, b'Hello Ardzy from the FPGA'), (1000000, bytes(range(256)))):
    P('/api/io/uart/config', baud=baud, tx='j1[1]', rx='j1[1]')
    P('/api/io/uart/read')
    P('/api/io/uart/send', hex=data.hex())
    time.sleep(0.2)
    r = P('/api/io/uart/read')
    got = bytes.fromhex(r['data_hex'])
    check('UART loopback %d baud (%d bytes)' % (baud, len(data)), got == data and not r['frame_error'],
          '%d bytes back' % len(got))

# 5. I2C buses answer (scan; nothing needs to be connected)
for bus in (1, 2):
    r = P('/api/i2c/scan', bus=bus)
    check('I2C bus %d scan' % bus, r.get('ok', True) and 'found' in r, 'devices: %s' % r.get('found'))

# back to rest: functions off, all pins inputs
P('/api/io/pwm/set', ch=0, release=1)
P('/api/io/pwm/set', ch=1, release=1)
for p in G('/api/io')['pins']:
    if p.get('func', 'gpio') != 'gpio':
        P('/api/io/func', name=p['name'], func='gpio')
    if p['mode'] != 'in' and not p['name'].startswith(('board_id', 'leds')):
        P('/api/io/set', name=p['name'], mode='in')
rest = G('/api/io')['pins']
check('all pins back to plain inputs', all(p.get('func', 'gpio') == 'gpio' for p in rest) and
      all(p['mode'] == 'in' for p in rest if p['name'].startswith('j')))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
