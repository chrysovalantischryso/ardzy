# Lesson 4: PWM. Python sets brightness 0..255 per LED; the FPGA measures its own duty cycle.
import math
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
CTRL, HIGH = 0x00, 0x80
WINDOW = 4194304                         # clocks in the measuring window

bad = []
for level in (0, 64, 128, 192, 255):
    regs.write(CTRL, level)
    time.sleep(0.12)
    duty = regs.read(HIGH) / WINDOW
    print('brightness %3d: LED 0 on %5.1f %% of the time (expected %5.1f %%)' % (level, 100 * duty, 100 * level / 256))
    if abs(duty - level / 256) > 0.002:
        bad.append(level)
check('measured duty = brightness / 256', not bad, 'wrong at %s' % bad if bad else '')
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nBreathing LEDs: each LED follows a sine, a quarter period after the one before.')
print('Our eyes see brightness roughly as the logarithm of light: squaring the sine makes the breath look even.')
t0 = time.time()
while True:
    t = time.time() - t0
    v = 0
    for i in range(4):
        s = (math.sin(2 * math.pi * (t / 3 - i / 4)) + 1) / 2
        v |= int(255 * s * s) << (8 * i)
    regs.write(CTRL, v)
    time.sleep(0.02)
