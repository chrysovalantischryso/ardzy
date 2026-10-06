# 06 Signal generator self-test: needs nothing connected. Checks the sine table against the formula,
# the other waves, amplitude and offset, the frequency measured at the sync pin, and a sweep.
import math
import time
from blocks import Bus, SignalGen, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'DDSG')
g = SignalGen(bus, slot=1)
check('signal generator answers', g.r(13) == 0x44445347)
g.on()
g.amplitude(1.0)
g.offset(0)
g.frequency(0)                                   # frozen phase: read samples at chosen phases
worst = 0
for w, f in (('sine', lambda p: 32767 * math.sin(2 * math.pi * p)),
             ('triangle', lambda p: (4 * p - 1) * 32767 if p < 0.5 else (3 - 4 * p) * 32767),
             ('saw', lambda p: (2 * p - 1) * 32767)):
    g.wave(w)
    err = 0
    for k in range(64):
        p = (k * 16 + 3) / 1024
        g.phase(p)
        time.sleep(0.0005)
        err = max(err, abs(g.sample() - f(p)))
    worst = max(worst, err)
    check('%s values at 64 phases' % w, err < 140, 'largest error %d of 32767' % err)
g.wave('square')
g.duty(0.25)
vals = []
for p in (0.1, 0.2, 0.3, 0.6):
    g.phase(p)
    time.sleep(0.0005)
    vals.append(g.sample())
check('square 25 % duty', vals[0] > 32000 and vals[1] > 32000 and vals[2] < -32000 and vals[3] < -32000, str(vals))
g.wave('sine')
g.phase(0.25)
g.amplitude(0.5)
g.offset(0.25)
time.sleep(0.0005)
s = g.sample()
check('amplitude 0.5 + offset 0.25', abs(s - (16383 + 8192)) < 40, '%d (want %d)' % (s, 16383 + 8192))
g.amplitude(1.0)
g.offset(0)
for hz in (1000, 123456, 2.5e6):
    g.frequency(hz)
    time.sleep(2.2)
    m = g.measured_hz()
    check('%g Hz measured at the sync pin' % hz, abs(m - hz) <= max(1, hz * 1e-6), '%d Hz' % m)
g.sweep(1000, 2000, seconds=1, repeat=False)
time.sleep(0.5)
mid = g.frequency()
time.sleep(0.8)
end = g.frequency()
check('sweep 1 -> 2 kHz in 1 s', 1300 < mid < 1700 and abs(end - 2000) < 5 and not g.r(0) & 2,
      'at 0.5 s %.0f Hz, at the end %.0f Hz' % (mid, end))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
