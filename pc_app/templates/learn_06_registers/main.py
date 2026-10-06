# Lesson 6: registers on the bus. Python writes A and B, the FPGA's answers are read back at once.
import random
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)
A, B = 0x00, 0x04
SUM, DIFF, PLO, PHI, MAX, AND, WRITES, NAME = (0x80 + 4 * i for i in range(8))
M = 0xFFFFFFFF

check('the design answers "LREG"', regs.read(NAME) == 0x4C524547, hex(regs.read(NAME)))
random.seed(6)
bad = 0
for _ in range(200):
    a, b = random.getrandbits(32), random.getrandbits(32)
    regs.write(A, a); regs.write(B, b)
    p = regs.read(PLO) | (regs.read(PHI) << 32)
    bad += (regs.read(SUM) != (a + b) & M or regs.read(DIFF) != (a - b) & M or p != a * b
            or regs.read(MAX) != max(a, b) or regs.read(AND) != a & b)
check('200 random A, B: +, -, *, max, AND all right', bad == 0, '%d wrong' % bad)

n = 20000
t = time.time()
for i in range(n):
    regs.read(SUM)
read_us = (time.time() - t) / n * 1e6
t = time.time()
for i in range(n):
    regs.write(A, i)
write_us = (time.time() - t) / n * 1e6
print('A register read takes %.2f us, a write %.2f us (from Python; from C it is about 0.2 us)' % (read_us, write_us))
check('register access works fast (under 20 us from Python)', read_us < 20 and write_us < 20)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nType two numbers in the Monitor (for example: 1234 5678) and the FPGA calculates.')
while True:
    try:
        a, b = (int(x, 0) for x in input().split()[:2])
    except (ValueError, EOFError):
        print('two numbers please, like: 12 34   or   0x10 7')
        continue
    regs.write(A, a); regs.write(B, b)
    print('A+B = %d   A-B = %d   A*B = %d   max = %d   A AND B = %d' % (
        regs.read(SUM), regs.read(DIFF) - (1 << 32 if regs.read(DIFF) >> 31 else 0),
        regs.read(PLO) | (regs.read(PHI) << 32), regs.read(MAX), regs.read(AND)), flush=True)
