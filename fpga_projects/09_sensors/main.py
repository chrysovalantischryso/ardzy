# 09 Sensors demo: distance, IR remote codes and touch, printed as they change. LED 0 = touched.
import time
from blocks import Bus, Sensors, require

bus = Bus()
info = require(bus, 'SENS')
s = Sensors(bus, slot=1)
s.setup(distance=True, touch=True)
print('Sensors on J8: HC-SR04 (pins 5/11), IR receiver (pin 12), touch pad (pin 15).')
last_ir, last_d, last_t = None, None, None
while True:
    d = s.distance_mm()
    if d != last_d and (d is None or last_d is None or abs(d - last_d) > 5):
        print('distance: %s' % ('%d mm' % d if d else 'nothing in range'), flush=True)
        last_d = d
    ir = s.ir()
    if ir['count'] != last_ir:
        if last_ir is not None:
            print('IR remote: address 0x%02X command 0x%02X%s' % (ir['address'], ir['command'], '' if ir['valid'] else ' (check bits wrong)'),
                  flush=True)
        last_ir = ir['count']
    t = s.touch()
    if t['touched'] != last_t:
        print('touch: %s (raw %d, base %d)' % ('TOUCHED' if t['touched'] else 'free', t['raw'], t['base']), flush=True)
        last_t = t['touched']
    info.leds(1 if t['touched'] else 0)
    time.sleep(0.05)
