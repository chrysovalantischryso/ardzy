# 05 SPI and I2C self-test: needs nothing connected.
# SPI: all 4 modes, both bit orders, 1..32-bit words through the loopback inside, speeds up to 50 MHz,
# and MISO reads the pull-up. I2C: the bus lines are high when idle, a scan runs at 100 / 400 / 1000 kHz.
import random
import time
from blocks import Bus, SPI, I2C, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'SPIC')
spi = SPI(bus, slot=1)
check('SPI block answers', spi.r(7) == 0x5350494D)
random.seed(3)
for mode in range(4):
    for lsb in (False, True):
        for bits in (8, 1, 13, 32):
            spi.setup(hz=25e6, mode=mode, bits=bits, lsb_first=lsb, loopback=True)
            data = [random.getrandbits(bits) for _ in range(40)]
            back = spi.transfer(data)
            ok = back == data
            if not ok or bits == 8:
                check('loopback mode %d %s %2d-bit words' % (mode, 'LSB' if lsb else 'MSB', bits), ok,
                      '%d of %d words right' % (sum(a == b for a, b in zip(back, data)), len(data)))
for hz in (1e6, 10e6, 50e6):
    spi.setup(hz=hz, mode=0, bits=8, loopback=True)
    data = list(range(64))
    t = time.time()
    back = spi.transfer(data)
    check('loopback at %g MHz (64 bytes)' % (hz / 1e6), back == data and abs(spi.hz() - hz) < 1, 'SCLK %.1f MHz' % (spi.hz() / 1e6))
spi.setup(hz=1e6, mode=0, bits=8, loopback=False)
back = spi.transfer([0x00, 0x55, 0xAA])
check('MISO pin with nothing connected reads 0xFF (pull-up)', back == [0xFF] * 3, ' '.join('%02X' % b for b in back))

i2c = I2C(bus, slot=2)
check('I2C block answers', i2c.r(5) == 0x4932434D)
ln = i2c.lines()
check('I2C lines high when idle (pull-ups)', ln['scl'] == 1 and ln['sda'] == 1, str(ln))
for hz in (100000, 400000, 1000000):
    i2c.speed(hz)
    t = time.time()
    found = i2c.scan()
    dt = time.time() - t
    ln = i2c.lines()
    check('scan at %d kHz, bus free afterwards' % (hz // 1000), ln['scl'] == 1 and ln['sda'] == 1 and not ln['timeout'],
          'found %s in %.2f s' % (['0x%02X' % a for a in found] or 'nothing', dt))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
