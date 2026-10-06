# fpga_ramtest: starts the RAM testers (see top.v) three times and prints the results
import time
from ardzy import MMIO

r = MMIO(0x41200000)
SHAPES = ['4096 x 32', '4096 x 9', '2048 x 9', '1024 x 18', '1024 x 36', '2048 x 18', '512 x 72',
          '32768 x 1', '16384 x 2', '8192 x 4', '8192 x 16']
print('magic %08x' % r.read(0x80))
total_ok = 0
for run in range(1, 4):
    r.write(0, 0)
    r.write(0, 1)                      # 0 -> 1 starts every tester
    time.sleep(0.05)                   # the biggest one needs about 0.7 ms
    done = r.read(0x84)
    bad = []
    for n, s in enumerate(SHAPES):
        v = r.read(0x88 + 4 * n)
        e = v & 0xFFFF
        if not (done >> n & 1) or e:
            bad.append('%s: %s' % (s, 'not finished' if not done >> n & 1 else '%d errors, first at %d' % (e, v >> 16)))
    ok = len(SHAPES) - len(bad)
    total_ok += ok
    print('run %d: %d of %d RAM shapes ok%s' % (run, ok, len(SHAPES), ('  FAIL ' + '; '.join(bad)) if bad else ''))
print('RESULT: %s' % ('all RAM shapes ok in 3 runs' if total_ok == 3 * len(SHAPES) else 'FAILURES'))
