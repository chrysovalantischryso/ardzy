# Lesson 9: frequencies. Python asks for a frequency, the FPGA makes it on a pin and measures it at the pin.
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
HALF, HZ, PERIOD, GATES = 0x00, 0x80, 0x84, 0x88


def measure(freq):
    half = max(1, round(50e6 / freq))
    regs.write(HALF, half)
    g = regs.read(GATES)
    while regs.read(GATES) < g + 2:          # wait for a whole gate with the new frequency
        time.sleep(0.05)
    return 50e6 / half, regs.read(HZ), regs.read(PERIOD)


bad = []
for f in (10, 1000, 123456, 5e6):
    want, hz, per = measure(f)
    print('asked %10.1f Hz: made %12.3f Hz, counted %10d Hz in 1 s, one period = %d clocks = %.3f Hz' % (f, want, hz, per, 100e6 / per))
    if abs(hz - want) > max(1, want * 1e-5) or abs(100e6 / per - want) > want * 1e-3:
        bad.append(f)
check('counted and period-measured = made', not bad, 'wrong at %s' % bad if bad else '')
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nWhich is better? At 10 Hz the 1-second count says "10", the period says "10.000": more digits.')
print('At 5 MHz the count has 7 digits, the period only 20 clocks (2 digits). Real counters use both.')
print('The signal stays on J1 pin 11 (1 kHz): look at it with a scope or the Tools logic analyzer later.')
regs.write(HALF, 50000)
while True:
    time.sleep(2)
    print('measuring: %d Hz' % regs.read(HZ), flush=True)
