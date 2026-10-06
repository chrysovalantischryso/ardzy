# 14 FIR filter lab self-test: every result equal to the integer math, the speed, and a low-pass filter's
# measured frequency response against the computed one.
import math
import random
import time
from blocks import Bus, FirLab, fir_design, fir_gain, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def model(coef, xs, shift):
    hist = [0] * 64
    out = []
    for x in xs:
        hist = [x] + hist[:-1]
        y = sum(c * v for c, v in zip(coef, hist)) >> shift
        out.append(max(-32768, min(32767, y)))
    return out


bus = Bus()
require(bus, 'FIR1')
fir = FirLab(bus, slot=1)
check('filter answers', fir.r(1023) == 0x46495231)

random.seed(14)
for taps in (1, 17, 64):
    fir.reset()
    q = [random.randint(-131072, 131071) for _ in range(taps)]
    fir.set_coef(q, 18)
    xs = [random.randint(-32768, 32767) for _ in range(300)]
    ys = fir.filter(xs)
    want = model(q, xs, 18)
    bad = sum(a != b for a, b in zip(ys, want)) + abs(len(ys) - len(want))
    check('%d taps: 300 random samples = the integer math' % taps, bad == 0, '%d different' % bad)

fir.reset()
h = fir_design('lowpass', f1=0.05, taps=63)
q = fir.set_filter(h)
FS = fir.generator(10e3, rate=68, amp=16000)
time.sleep(0.2)
s = fir.status()
t0, n0 = time.time(), s['samples']
time.sleep(0.5)
rate = (fir.status()['samples'] - n0) / (time.time() - t0)
check('63 taps at full speed: 1.47 million samples/s', abs(rate - 100e6 / 68) < 0.01 * 100e6 / 68, '%.3f million/s' % (rate / 1e6))

fir.reset()
fir.set_filter(h)
FS = 1e6
bad = []
for f in (5e3, 30e3, 80e3, 150e3, 300e3):
    g = fir.response([f], rate=100, seconds=0.02)[0]
    want = fir_gain(q, f / FS) / (1 << fir.SHIFT)
    gdb, wdb = 20 * math.log10(max(g, 1e-5)), 20 * math.log10(max(want, 1e-5))
    if (wdb > -40 and abs(gdb - wdb) > 0.5) or (wdb <= -40 and gdb > -38):
        bad.append('%.0f kHz %.1f/%.1f dB' % (f / 1e3, gdb, wdb))
check('low-pass response measured = computed', not bad, ', '.join(bad))

pairs = fir.capture(200)
check('capture: 200 (input, output) pairs', len(pairs) == 200, str(len(pairs)))
s = fir.status()
check('nothing clipped, nothing lost', s['clipped'] == 0 and s['lost'] == 0, '%d clipped, %d lost' % (s['clipped'], s['lost']))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
