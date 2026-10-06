# 02 Pattern generator demo: a few useful patterns on J5..J8. Look at them with a scope or a logic analyzer.
#   pin 0..3 = J5, 4..7 = J6, 8..11 = J7, 12..15 = J8 (pins 5, 11, 12, 15 of each connector)
import time
from blocks import Bus, PatternGen, require

bus = Bus()
info = require(bus, 'PATG')
pg = PatternGen(bus, slot=1)
pg.outputs(0xFFFF)                       # all 16 pins are outputs

demos = [
    ('8-bit counter on pins 0..7, 1 MHz steps', [i & 0xFF for i in range(256)], 1e6),
    ('walking one over 16 pins, 100 kHz steps', [1 << (i % 16) for i in range(16)], 1e5),
    ('SPI-like frame: CS (pin 0) low, 8 clocks (pin 1), data 0xA5 (pin 2)',
     [1] + [2 * (k & 1) | 4 * ((0xA5 >> (7 - k // 2)) & 1) for k in range(16)] + [1, 1], 2e6),
    ('PWM 25 % / 50 % / 75 % on pins 0, 1, 2 at 1 MHz (100 steps)',
     [(i < 25) | (i < 50) << 1 | (i < 75) << 2 for i in range(100)], 100e6),
    ('Gray code on pins 0..3, 10 MHz steps', [i ^ (i >> 1) for i in range(16)], 10e6),
]
print('Pattern generator demo on J5..J8. Stop with the Stop button.')
while True:
    for n, (name, steps, rate) in enumerate(demos):
        info.leds(1 << (n % 4))
        pg.stop()
        pg.load(steps)
        pg.rate(rate)
        pg.start(loop=True)
        time.sleep(3)
        s = pg.status()
        print('%-60s %d loops, %d pin mismatches' % (name, s['loops'], s['mismatches']), flush=True)
