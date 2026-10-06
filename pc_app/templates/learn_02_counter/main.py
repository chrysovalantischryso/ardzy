# Lesson 2: the clock and a counter. Python measures how fast the FPGA counts, then picks which bits blink.
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
CTRL, COUNT, BLINKS = 0x00, 0x80, 0x84

c0, t0 = regs.read(COUNT), time.time()
time.sleep(1.0)
c1, t1 = regs.read(COUNT), time.time()
rate = ((c1 - c0) & 0xFFFFFFFF) / (t1 - t0)
print('The counter went from %d to %d in %.3f s: %.1f million counts per second' % (c0, c1, t1 - t0, rate / 1e6))
check('the counter counts at the clock: 100 MHz', abs(rate - 100e6) < 2e6, '%.2f MHz' % (rate / 1e6))
b0 = regs.read(BLINKS)
time.sleep(3.0)
blinks = regs.read(BLINKS) - b0
check('bit 26 toggles 100e6 / 2^27 = 0.745 times per second', 1 <= blinks <= 3, '%d rising edges in 3 s' % blinks)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nThe LEDs show 4 bits of the counter. Bit n blinks 100 000 000 / 2^(n+1) times per second:')
for n in (20, 22, 23, 24):
    regs.write(CTRL, n)
    print('  LEDs = bits %d .. %d  (LED 0 blinks %.1f times per second)' % (n, n + 3, 100e6 / 2 ** (n + 1)), flush=True)
    time.sleep(4)
regs.write(CTRL, 23)
print('Left at bits 23 .. 26: a binary counter you can watch. Change the numbers above and upload again.')
while True:
    time.sleep(1)
