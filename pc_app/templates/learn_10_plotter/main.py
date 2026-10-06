# Lesson 10: your own instrument. Python sets the oscillator, reads it and prints for the Plotter.
# Open the bottom panel's Plotter tab: lines like  wave:123  are drawn as a graph.
import math
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
STEP, AMP, WAVE, PHASE = 0x00, 0x04, 0x80, 0x84


def s16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v


def set_osc(freq, amp=30000, shape=0):
    regs.write(STEP, round(freq / 100e6 * 2 ** 32))
    regs.write(AMP, (shape << 16) | amp)


set_osc(1000)
p0, t0 = regs.read(PHASE), time.time()
time.sleep(0.5)
p1, t1 = regs.read(PHASE), time.time()
cycles = ((p1 - p0) & 0xFFFFFFFF) / 2 ** 32       # (the phase wraps 500 times in 0.5 s at 1 kHz; this counts within one)
set_osc(0.5)                                         # slow: 0.5 Hz
peak = 0
t = time.time()
while time.time() - t < 2.2:
    peak = max(peak, abs(s16(regs.read(WAVE))))
check('a 0.5 Hz sine reaches its amplitude (30000)', abs(peak - 30000) < 300, 'peak %d' % peak)
set_osc(0.5, 30000, 3)
v = set()
t = time.time()
while time.time() - t < 2.2:                         # a whole period (about 2 s)
    v.add(s16(regs.read(WAVE)))
check('the square wave has 2 levels, +30000 and -30000', len(v) == 2 and all(abs(abs(x) - 30000) < 5 for x in v), str(sorted(v)))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nOpen the Plotter tab. Every 4 seconds the shape changes: sine, triangle, sawtooth, square.')
shapes = ['sine', 'triangle', 'sawtooth', 'square']
n = 0
while True:
    set_osc(0.5, 30000, n % 4)
    print('now: %s' % shapes[n % 4], flush=True)
    t = time.time()
    while time.time() - t < 4:
        print('wave:%d' % s16(regs.read(WAVE)), flush=True)
        time.sleep(0.04)
    n += 1
