# 04 Steppers self-test: needs nothing connected (it makes step pulses on J8 pins 5 and 12 and counts
# them back at the pins). Checks exact stops, the speed profile and the stop commands.
import math
import time
from blocks import Bus, Stepper, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'STEP')
x = Stepper(bus, slot=1, axis=0)
y = Stepper(bus, slot=1, axis=1)
check('stepper block answers', x.r(64) == 0x53544550)
for ax in (x, y):
    ax.setup(max_speed=20000, accel=40000, start_speed=500)
    ax.position(0)
    ax.pin_steps(clear=True)

t = time.time()
x.move_to(10000)
peak = 0
while x.moving():
    peak = max(peak, x.speed())
dt = time.time() - t
# trapezoid: accelerate to 20000 in 0.5 s (5000 steps), cruise 0 steps, slow down 5000 steps: about 1.0 s
check('10000 steps forward: stops exactly', x.position() == 10000 and x.pin_steps() == 10000,
      'position %d, %d pulses at the pin' % (x.position(), x.pin_steps()))
check('top speed reached (20000 steps/s)', abs(peak - 20000) < 300, '%.0f steps/s' % peak)
check('time like the speed profile (about 1.0 s)', 0.85 < dt < 1.25, '%.2f s' % dt)
x.pin_steps(clear=True)
x.move_to(-3000)
x.wait()
check('back to -3000 (direction change)', x.position() == -3000 and x.pin_steps() == 13000,
      'position %d, %d pulses' % (x.position(), x.pin_steps()))
x.move_to(1000000)                       # long move, then a smooth stop
time.sleep(0.3)
x.stop()
x.wait()
p = x.position()
check('smooth stop on request', -3000 < p < 1000000 and not x.moving(), 'stopped at %d' % p)
x.move_to(p + 500000)
time.sleep(0.2)
x.stop(now=True)
time.sleep(0.01)
check('stop at once', not x.moving() and x.target() == x.position(), 'at %d' % x.position())
y.move_to(64)                            # short move: never reaches top speed
y.wait()
check('short move (64 steps) on axis 1', y.position() == 64 and y.pin_steps() == 64,
      '%d, %d pulses' % (y.position(), y.pin_steps()))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
