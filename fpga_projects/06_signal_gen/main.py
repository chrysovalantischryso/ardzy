# 06 Signal generator demo: steps through the waves, then sweeps 100 Hz .. 10 kHz over and over.
# Analog output: J6 pin 5 through 1 kohm + 10 nF. Square sync: J6 pin 12.
import time
from blocks import Bus, SignalGen, require

bus = Bus()
info = require(bus, 'DDSG')
g = SignalGen(bus, slot=1)
g.amplitude(0.9)
g.offset(0)
g.on()
print('Signal generator on J6. Stop with the Stop button.')
while True:
    for n, w in enumerate(('sine', 'triangle', 'saw', 'square')):
        info.leds(1 << n)
        g.sweep_off()
        g.wave(w)
        g.frequency(1000)
        time.sleep(2.2)
        print('%-8s 1000 Hz, measured at the sync pin: %d Hz' % (w, g.measured_hz()), flush=True)
    g.wave('sine')
    g.sweep(100, 10000, seconds=5, repeat=True)
    print('sine sweep 100 Hz .. 10 kHz every 5 s', flush=True)
    for _ in range(5):
        time.sleep(2)
        print('  now %.0f Hz' % g.frequency(), flush=True)
