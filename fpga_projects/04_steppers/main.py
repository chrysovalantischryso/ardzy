# 04 Steppers demo: axis 0 moves back and forth with smooth acceleration; axis 1 follows at half speed.
# 200 steps per turn x 16 microsteps = 3200 steps per motor turn (set your driver's jumpers).
import time
from blocks import Bus, Stepper, require

TURN = 3200
bus = Bus()
info = require(bus, 'STEP')
x = Stepper(bus, slot=1, axis=0)
y = Stepper(bus, slot=1, axis=1)
x.setup(max_speed=8000, accel=16000, start_speed=200)       # steps/s, steps/s^2
y.setup(max_speed=4000, accel=8000, start_speed=200)
x.position(0)
y.position(0)
print('Stepper demo: axis 0 on J8 pins 5/11, axis 1 on J8 pins 12/15. Stop with the Stop button.')
n = 0
while True:
    n += 1
    target = 2 * TURN if n % 2 else 0
    t = time.time()
    x.move_to(target)
    y.move_to(target // 2)
    info.leds(1 if target else 2)
    top = 0
    while x.moving() or y.moving():
        top = max(top, x.speed())
        time.sleep(0.01)
    print('move %d: axis 0 at %d, axis 1 at %d, %.2f s, top speed %.0f steps/s, pulses seen %d'
          % (n, x.position(), y.position(), time.time() - t, top, x.pin_steps()), flush=True)
    time.sleep(0.5)
