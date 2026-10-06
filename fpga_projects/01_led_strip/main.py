# 01 LED strip demo: rainbow, colour wipe, theatre chase and a breathing glow on a WS2812B strip.
# Change N to the number of LEDs on your strip. Stop with the Stop button.
import time
from blocks import Bus, LedStrip, require, rgb, wheel

N = 60                       # LEDs on your strip
bus = Bus()
info = require(bus, 'LEDS')
strip = LedStrip(bus, slot=1, count=N)
strip.timing()               # WS2812B (for SK6812: strip.timing(300, 600, 1250, 80))
strip.order('GRB')
strip.brightness(64)         # 25 %: easy on the eyes and on the power supply

print('LED strip demo on J7 pin 5, %d LEDs. Stop with the Stop button.' % N)
while True:
    info.leds(1)
    for step in range(0, 256, 2):                      # rainbow
        strip.write(wheel(i * 256 // N + step) for i in range(N))
        strip.show()
        time.sleep(0.02)
    info.leds(2)
    for color in (rgb(255, 0, 0), rgb(0, 255, 0), rgb(0, 0, 255)):   # colour wipe
        for i in range(N):
            strip.set(i, color)
            strip.show()
            time.sleep(0.01)
    info.leds(4)
    for k in range(30):                                # theatre chase
        strip.write(rgb(255, 160, 0) if (i + k) % 3 == 0 else 0 for i in range(N))
        strip.show()
        time.sleep(0.06)
    info.leds(8)
    strip.fill(rgb(0, 80, 255))                        # breathing
    for b in list(range(0, 128, 4)) + list(range(128, 0, -4)):
        strip.brightness(b)
        strip.show()
        time.sleep(0.02)
    strip.brightness(64)
    s = strip.pin_stats()
    print('frames sent %d, last frame: %d pulses at the pin, 0-bit %d ns, 1-bit %d ns'
          % (strip.frames(), s['pulses'], s['short_ns'], s['long_ns']), flush=True)
