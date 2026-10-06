# 01 LED strip self-test: needs nothing connected. Sends frames and checks, at the pin itself,
# the number of pulses and their lengths (the FPGA reads its own pin back).
import time
from blocks import Bus, LedStrip, require, rgb

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-44s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
info = require(bus, 'LEDS')
check('design loaded (project LEDS)', True, 'running for %d s' % info.seconds())
info.leds(0b0101)
check('board LEDs register', info.leds() == 0b0101)
info.leds(0)
strip = LedStrip(bus, slot=1)
check('LED strip block answers', strip.r(11) == 0x57533238)
for n, color in ((1, rgb(255, 255, 255)), (10, rgb(0x12, 0x34, 0x56)), (300, rgb(255, 0, 0))):
    strip.count(n)
    strip.brightness(255)
    strip.timing()
    strip.fill(color, n)
    f0 = strip.frames()
    t = time.time()
    strip.show()
    dt = time.time() - t
    s = strip.pin_stats()
    ones = bin(color).count('1') * n                  # 1-bits sent (GRB order has the same count)
    check('%d LEDs: %d pulses at the pin' % (n, 24 * n), s['pulses'] == 24 * n and strip.frames() == f0 + 1,
          '%d pulses, frame took %.2f ms' % (s['pulses'], dt * 1000))
    if ones < 24 * n:
        check('  0-bit high time 400 ns (+-10)', abs(s['short_ns'] - 400) <= 10, '%d ns' % s['short_ns'])
    check('  1-bit high time 800 ns (+-10)', abs(s['long_ns'] - 800) <= 10, '%d ns' % s['long_ns'])
strip.count(8)                                          # SK6812 timing
strip.timing(300, 600, 1250, 80)
strip.fill(rgb(0x0F, 0xF0, 0x0F), 8)
strip.show()
s = strip.pin_stats()
check('SK6812 timing: 300 / 600 ns', abs(s['short_ns'] - 300) <= 20 and abs(s['long_ns'] - 600) <= 20,
      '%d / %d ns' % (s['short_ns'], s['long_ns']))
strip.brightness(0)                                     # brightness 0: every bit is a 0
strip.timing()
strip.show()
s = strip.pin_stats()
check('brightness 0 sends only 0-bits', s['pulses'] == 24 * 8 and abs(s['short_ns'] - 400) <= 20)
strip.brightness(64)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
