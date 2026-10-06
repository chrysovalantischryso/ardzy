# 03 Encoders demo: shows both encoders' position and speed, and the position on the 4 LEDs.
# Turn a knob on J5 (encoder 0: pins 5 and 11, encoder 1: pins 12 and 15). Stop with the Stop button.
import time
from blocks import Bus, Encoders, require

bus = Bus()
info = require(bus, 'QUAD')
enc = Encoders(bus, slot=1)
enc.test(internal=False, drive_pins=False)
enc.gate(0.1)
for ch in (0, 1):
    enc.config(ch, reverse=False, filter_ns=1000)      # 1 us filter: good for mechanical knobs
print('Turn the encoders on J5. Positions are in counts (4 per click on most knobs).')
last = None
while True:
    p0, p1 = enc.count(0), enc.count(1)
    info.leds(1 << ((p0 // 4) % 4))
    now = (p0, p1)
    if now != last:
        print('encoder 0: %7d (%+8.0f /s, %d errors)    encoder 1: %7d (%+8.0f /s, %d errors)'
              % (p0, enc.speed(0), enc.errors(0), p1, enc.speed(1), enc.errors(1)), flush=True)
        last = now
    time.sleep(0.1)
