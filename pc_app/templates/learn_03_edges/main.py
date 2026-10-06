# Lesson 3: edges and debouncing. Python presses a "button" (and makes it bounce); the FPGA counts clean presses.
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
CTRL, PRESSES, BOUNCES = 0x00, 0x80, 0x84

p0 = regs.read(PRESSES)
for i in range(5):
    regs.write(CTRL, 1); time.sleep(0.05)
    regs.write(CTRL, 0); time.sleep(0.05)
check('5 clean presses counted as 5', regs.read(PRESSES) - p0 == 5, '%d' % (regs.read(PRESSES) - p0))

p0, b0 = regs.read(PRESSES), regs.read(BOUNCES)
for i in range(3):                       # a bouncy press: 6 quick changes, then held
    for _ in range(3):
        regs.write(CTRL, 1); regs.write(CTRL, 0)
    regs.write(CTRL, 1); time.sleep(0.05)
    regs.write(CTRL, 0); time.sleep(0.05)
dp, db = regs.read(PRESSES) - p0, regs.read(BOUNCES) - b0
check('3 bouncy presses still count as 3', dp == 3, '%d presses, %d raw changes seen' % (dp, db))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nConnect a button between J1 pin 5 and GND (pin 1) and press it: LED 0 toggles at every press.')
regs.write(CTRL, 2)                      # use the pin
last = regs.read(PRESSES)
while True:
    p = regs.read(PRESSES)
    if p != last:
        print('press %d (raw changes so far: %d: the bounces the debouncer hid)' % (p, regs.read(BOUNCES)), flush=True)
        last = p
    time.sleep(0.05)
