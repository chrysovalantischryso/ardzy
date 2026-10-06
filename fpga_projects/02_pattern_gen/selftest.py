# 02 Pattern generator self-test: needs nothing connected. Every step is checked at the pins themselves
# (the FPGA reads its own outputs back), at speeds up to 100 million steps per second.
import random
import time
from blocks import Bus, PatternGen, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'PATG')
pg = PatternGen(bus, slot=1)
check('pattern generator answers', pg.r(9) == 0x50415447)
random.seed(7)
table = [random.getrandbits(16) for _ in range(1024)]
pg.outputs(0xFFFF)
pg.load(table)
check('table length register', pg.r(1) == 1024)
for rate in (1e6, 10e6, 50e6, 100e6):
    pg.stop()
    pg.rate(rate)
    pg.start(loop=True)
    time.sleep(0.3)
    s = pg.status()
    pg.stop()
    expect = 0.3 * rate / 1024
    check('random 16-pin table at %g steps/s' % rate, s['mismatches'] == 0 and s['loops'] > expect * 0.5,
          '%d loops played, %d pin mismatches' % (s['loops'], s['mismatches']))
pg.load([1, 2, 4, 8])                    # single run: plays once and stops
pg.rate(1e6)
pg.start(loop=False)
time.sleep(0.01)
check('single run stops by itself', not pg.running() and pg.r(6) == 1)
pg.idle(0x5A5A)
time.sleep(0.001)
check('idle levels when stopped', pg.status()['inputs'] == 0x5A5A, '0x%04x' % pg.status()['inputs'])
pg.outputs(0)                            # all inputs: the pull-ups make them read 1
time.sleep(0.001)
check('outputs off: pins float high (pull-ups)', pg.status()['inputs'] == 0xFFFF, '0x%04x' % pg.status()['inputs'])
print('RESULT: %d of %d ok' % (sum(results), len(results)))
