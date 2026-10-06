# fpga_selftest: reads what the FPGA measured about itself (see top.v) and tests block RAM and DSP
# from the ARM. Every line says ok / FAIL.
import time
from ardzy import MMIO

r = MMIO(0x41200000)
S = 0x80
results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-46s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def st(n):
    return r.read(S + 4 * n)


def near(value, want, tol=0.001):
    return abs(value - want) <= want * tol


time.sleep(0.5)
check('design answers (magic STST)', st(0) == 0x53545354, '0x%08x' % st(0))
t0 = time.time()
while (st(1) >> 16) < 3 and time.time() - t0 < 3:      # wait for 3 measuring gates (0.3 s)
    time.sleep(0.05)
f = st(1)
check('MMCM locked', bool(f & 1))
check('PLL locked', bool(f & 2))
names = [('MMCM 25 MHz', 6, 25e6), ('MMCM 100 MHz', 7, 100e6), ('MMCM 125 MHz', 8, 125e6), ('MMCM 200 MHz', 9, 200e6),
         ('PLL 50 MHz', 10, 50e6), ('PLL 133.33 MHz', 11, 400e6 / 3), ('clock switch (BUFGCTRL) at 25 MHz', 12, 25e6),
         ('fabric output -> LED pin 0 (12.5 MHz)', 13, 12.5e6), ('DDR output ODDR -> LED pin 1', 14, 25e6)]
for name, idx, want in names:
    hz = st(idx) * 10
    check(name, near(hz, want), '%.6f MHz measured' % (hz / 1e6))

# clock switch to the PLL's 50 MHz
r.write(0, 1 << 16)
time.sleep(0.35)
hz = st(12) * 10
check('clock switch (BUFGCTRL) at 50 MHz', near(hz, 50e6) and bool(st(1) & 16), '%.6f MHz measured' % (hz / 1e6))
r.write(0, 0)

check('block RAM self-test (4096 x 32, 4 x RAMB36)', bool(f & 4) and st(2) == 0, '%d errors' % st(2))
bad = 0
for a in (0, 1, 1234, 4095):                       # the self-test pattern, read by the ARM
    r.write(0, a)
    time.sleep(0.001)
    want = (a << 20) | ((~a & 0xFFF) << 8) | 0xA5
    bad += st(3) != want
for a, v in ((7, 0xDEADBEEF), (4000, 0x12345678)):  # write from the ARM, read back
    r.write(4, v)
    r.write(0, a)
    r.write(0, a | 1 << 31)
    r.write(0, a)
    time.sleep(0.001)
    bad += st(3) != v
check('block RAM read / write from the ARM', bad == 0, '%d wrong words' % bad)

bad = 0
for a, b in ((3, 7), (-12345, 678), (16777215, -131072), (-16777216, 131071)):
    r.write(8, a & 0xFFFFFFFF)
    r.write(12, b & 0xFFFFFFFF)
    time.sleep(0.001)
    p = st(4) | (st(5) << 32)
    if p >= 1 << 63:
        p -= 1 << 64
    bad += p != a * b
check('DSP48E1 multiply 25 x 18 bit (4 cases)', bad == 0, '%d wrong' % bad)
srl, lram = st(15) & 0xFFFF, st(15) >> 16
check('shift register (SRLC32E) self-test', srl == 0, '%d errors' % srl)
check('LUT RAM self-test', bool(f & 8) and lram == 0, '%d errors' % lram)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)
