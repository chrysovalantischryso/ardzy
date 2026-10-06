# 07 VGA demo: a status screen with the board's temperature graph, a clock and colour bars.
import math
import os
import time
from blocks import Bus, VGA, require

bus = Bus()
info = require(bus, 'VGA6')
v = VGA(bus, slot=1)
v.on()


def temperature():
    for p in ('/sys/bus/iio/devices/iio:device0/in_temp0_raw',):
        try:
            raw = int(open(p).read())
            off = int(open(p.replace('_raw', '_offset')).read())
            sc = float(open(p.replace('_raw', '_scale')).read())
            return (raw + off) * sc / 1000
        except OSError:
            pass
    return 0.0


temps = []
print('VGA demo: connect a monitor (see the guide). Stop with the Stop button.')
while True:
    temps = (temps + [temperature()])[-280:]
    v.clear(v.BLUE)
    v.rect(0, 0, 320, 20, v.DARKGREY)
    v.text(6, 6, 'ARDZY  Antminer S9 Zynq board', v.YELLOW)
    v.text(232, 6, time.strftime('%H:%M:%S'), v.WHITE)
    v.text(8, 30, 'Chip temperature: %.1f C' % temps[-1], v.LCYAN, scale=1)
    v.rect(20, 50, 282, 120, v.BLACK)
    for y in range(50, 170, 20):
        v.line(20, y, 301, y, v.DARKGREY)
    lo, hi = 30.0, 80.0
    pts = [(21 + i, 169 - int((t - lo) / (hi - lo) * 118)) for i, t in enumerate(temps)]
    for a, b in zip(pts, pts[1:]):
        v.line(a[0], a[1], b[0], b[1], v.LGREEN)
    v.text(24, 54, '%.0f C' % hi, v.GREY)
    v.text(24, 158, '%.0f C' % lo, v.GREY)
    for c in range(16):
        v.rect(8 + c * 19, 182, 18, 22, c)
    v.text(8, 214, 'up %d s   frames %d' % (info.seconds(), v.sync_check()['frames']), v.WHITE)
    v.show()
    info.leds(1 << (len(temps) % 4))
    time.sleep(1)
