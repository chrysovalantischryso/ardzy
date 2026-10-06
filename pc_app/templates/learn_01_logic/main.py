# Lesson 1: logic gates. Python sets the inputs a, b, c; the FPGA answers with AND, OR, XOR and MAJORITY.
import time
from ardzy import MMIO
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)

regs = MMIO(0x41200000)                  # the design's registers (ardzy_soc)
CTRL, STATUS = 0x00, 0x80

print('Truth table: what the FPGA computes for every input')
print('  a b c | AND OR XOR MAJ')
bad = 0
for n in range(8):
    a, b, c = n & 1, (n >> 1) & 1, (n >> 2) & 1
    regs.write(CTRL, n)                  # the inputs go to the FPGA
    f = regs.read(STATUS)                # its answers come back
    got = [(f >> i) & 1 for i in range(4)]
    want = [a & b, a | b, a ^ b, int(a + b + c >= 2)]
    bad += got != want
    print('  %d %d %d |  %d   %d   %d   %d' % (a, b, c, *got))
check('all 8 rows equal Python\'s logic', bad == 0, '%d wrong' % bad)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nNow the LEDs count through the inputs once a second: watch AND, OR, XOR and MAJ change.')
n = 0
while True:
    regs.write(CTRL, n % 8)
    print('inputs a=%d b=%d c=%d  -> LEDs %s' % (n & 1, (n >> 1) & 1, (n >> 2) & 1, format(regs.read(STATUS), '04b')), flush=True)
    n += 1
    time.sleep(1)
