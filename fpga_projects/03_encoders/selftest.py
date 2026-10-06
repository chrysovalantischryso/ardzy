# 03 Encoders self-test. Part 1 uses the generator inside the FPGA; part 2 lets the generator drive
# encoder 0's real pins (J5 pins 5 and 11) and counts what comes back: nothing may be connected there.
import time
from blocks import Bus, Encoders, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'QUAD')
enc = Encoders(bus, slot=1)
check('encoder block answers', enc.r(69) == 0x51554144)
enc.gate(0.1)
for ch in (0, 1):
    enc.config(ch, filter_ns=200)
    enc.count(ch, 0)

enc.test(internal=True)            # switching from the pins (both high) to the generator (both low)
time.sleep(0.01)                   # changes A and B at once: that is counted as one error, correctly
err0 = enc.errors(0)
for ch in (0, 1):
    enc.count(ch, 0)
enc.generate(steps=10000, counts_per_second=1e6)
time.sleep(0.05)
check('inside: 10000 steps forward at 1 MHz', enc.count(0) == 10000 and enc.count(1) == 10000,
      '%d / %d' % (enc.count(0), enc.count(1)))
enc.generate(steps=2500, counts_per_second=1e6, backwards=True)
time.sleep(0.05)
check('inside: 2500 steps back, no errors', enc.count(0) == 7500 and enc.errors(0) == err0,
      '%d, %d errors' % (enc.count(0), enc.errors(0) - err0))
enc.config(1, reverse=True)
enc.count(1, 0)
enc.generate(steps=1000, counts_per_second=1e6)
time.sleep(0.05)
check('reverse direction setting', enc.count(1) == -1000, '%d' % enc.count(1))
enc.config(1, reverse=False)
enc.generate(steps=0, counts_per_second=200000)                 # run on: measure the speed
time.sleep(0.35)
sp = enc.speed(0)
check('speed measurement 200,000 counts/s', abs(sp - 200000) < 100, '%.0f counts/s' % sp)
enc.generate(steps=1, counts_per_second=1e6)
time.sleep(0.01)
enc.count(0, 0)
enc.config(0, filter_ns=200)
enc.generate(steps=5000, counts_per_second=20e6)                # 20 MHz steps: faster than the filter
time.sleep(0.01)
check('filter rejects steps shorter than 200 ns', enc.count(0) != 5000, 'counted %d of 5000 (expected fewer)' % enc.count(0))

enc.test(internal=False, drive_pins=True)                        # real pins
time.sleep(0.01)
enc.config(0, filter_ns=200)
enc.count(0, 0)
e0 = enc.errors(0)
enc.generate(steps=50000, counts_per_second=2e6)
time.sleep(0.1)
check('pins J5/5 + J5/11: 50000 steps at 2 MHz', enc.count(0) == 50000 and enc.errors(0) == e0,
      '%d counted, %d errors' % (enc.count(0), enc.errors(0) - e0))
enc.generate(steps=50000, counts_per_second=2e6, backwards=True)
time.sleep(0.1)
check('pins: back to 0', enc.count(0) == 0, '%d' % enc.count(0))
enc.test(internal=False, drive_pins=False)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
