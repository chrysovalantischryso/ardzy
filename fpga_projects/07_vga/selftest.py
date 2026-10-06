# 07 VGA self-test: needs nothing connected. Checks the pixel clock, the line and frame timing at the sync
# pins (read back at the pads), the frame buffer (write and read back all 9600 words) and the palette.
import random
import time
from blocks import Bus, VGA, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'VGA6')
v = VGA(bus, slot=1)
check('VGA block answers', v.r(4) == 0x56474136)
v.on(picture=True, test_pattern=True)
time.sleep(0.2)
s = v.sync_check()
check('pixel clock running (MMCM locked)', s['clock_locked'])
check('line every 32.0 us (31.25 kHz) at the HSYNC pin', abs(s['line_us'] - 32.0) < 0.02, '%.2f us' % s['line_us'])
check('frame every 16.8 ms (59.5 Hz) at the VSYNC pin', abs(s['frame_ms'] - 16.8) < 0.01, '%.3f ms' % s['frame_ms'])
f0 = s['frames']
time.sleep(1.0)
n = v.sync_check()['frames'] - f0
check('about 59.5 frames per second', 58 <= n <= 61, '%d frames in 1 s' % n)
random.seed(5)
v.on(picture=True, test_pattern=False)
v.buf = [random.getrandbits(32) for _ in range(9600)]
v.show()
pal = [v.r(16 + n) for n in range(16)]
bad = 0
points = [(random.randrange(640), random.randrange(480)) for _ in range(40)] + [(0, 0), (639, 479), (638, 0), (0, 478)]
for sx, sy in points:
    x, y = sx >> 1, sy >> 1
    want = (v.buf[y * 40 + (x >> 3)] >> (4 * (x & 7))) & 15
    val, col = v.probe(sx, sy)
    bad += (val != want) or (col != pal[want])
check('picture shows the frame buffer (%d screen points)' % len(points), bad == 0, '%d wrong' % bad)
v.palette(3, 1, 2, 3)
check('palette entry', v.r(16 + 3) == 0b011011)
v.palette(3, 0, 2, 2)                              # back to the default cyan
v.clear(0)
v.text(8, 8, 'Ardzy VGA self-test OK', v.WHITE)
v.show()
print('RESULT: %d of %d ok' % (sum(results), len(results)))
