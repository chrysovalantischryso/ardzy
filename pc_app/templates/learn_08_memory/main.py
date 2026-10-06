# Lesson 8: block RAM. Python fills the FPGA's memory with a light show; the FPGA plays it back.
import random
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
ADDR, DATA, PLAY = 0x00, 0x04, 0x08
RDATA, STEP, SUM = 0x80, 0x84, 0x88


def poke(addr, value):
    regs.write(ADDR, addr)
    regs.write(DATA, value ^ 0xFFFFFFFF)     # (a different value first, so the write is seen even if equal)
    regs.write(DATA, value)


def peek(addr):
    regs.write(ADDR, addr)
    return regs.read(RDATA)


random.seed(8)
words = [random.getrandbits(32) for _ in range(1024)]
for a, w in enumerate(words):
    poke(a, w)
bad = sum(peek(a) != w for a, w in enumerate(words))
check('1024 words written and read back', bad == 0, '%d wrong' % bad)
time.sleep(0.01)
check('the FPGA\'s checksum = Python\'s sum', regs.read(SUM) == sum(words) & 0xFFFFFFFF,
      '%08x / %08x' % (regs.read(SUM), sum(words) & 0xFFFFFFFF))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nA light show from memory: a bouncing light, then all LEDs counting in binary.')
show = []
for p in [1, 2, 4, 8, 4, 2] * 3:
    show.append((p, 120))                  # (LEDs, milliseconds)
for n in range(16):
    show.append((n, 200))
for i, (leds, ms) in enumerate(show):
    poke(i, (ms << 8) | leds)
regs.write(PLAY, (1 << 31) | len(show))
print('%d steps playing on their own, the ARM does nothing now. Step number now:' % len(show))
while True:
    print('  step %d' % regs.read(STEP), flush=True)
    time.sleep(1)
