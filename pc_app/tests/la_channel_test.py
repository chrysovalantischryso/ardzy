"""Logic analyzer channel test on a real board (pin-control design loaded), drives nothing:
capture the pins at rest and compare every channel with the live pin levels.
A channel stuck at 0 or 1 in the capture memory shows up as a mismatch.

    python la_channel_test.py [host]
"""
import json, sys, time, urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else 'ardzy.local'


def call(method, path):
    req = urllib.request.Request('http://%s%s' % (HOST, path), method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


bad_total = 0
for run, rate in enumerate((1000000, 100000, 25000000), 1):
    io = call('GET', '/api/io')
    levels = [p['level'] for p in io['pins']]
    call('POST', '/api/la/start?rate=%d&pre=10' % rate)
    for _ in range(50):
        time.sleep(0.1)
        if call('GET', '/api/la')['done']:
            break
    d = call('GET', '/api/la/data')
    io2 = call('GET', '/api/io')
    levels2 = [p['level'] for p in io2['pins']]
    names = d['signals']
    bad = set()
    for k, lo, hi in d['changes']:
        v = lo | hi << 32
        for i, (a, b) in enumerate(zip(levels, levels2)):
            if a == b and (v >> i & 1) != a:          # a pin that did not change while capturing
                bad.add(names[i])
    bad_total += len(bad)
    print('capture %d at %g Hz: %d sample groups, %d pins compared, %s' % (
        run, rate, len(d['changes']), sum(a == b for a, b in zip(levels, levels2)),
        'all channels match the pins' if not bad else 'MISMATCH on ' + ', '.join(sorted(bad))))
print('RESULT:', 'ok' if bad_total == 0 else 'FAIL')
