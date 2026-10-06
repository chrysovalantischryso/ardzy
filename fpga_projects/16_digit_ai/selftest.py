# 16 AI in the FPGA self-test: the engine against the Python integer math, bit for bit, and the speed.
import time
import numpy as np
import nn_model
from blocks import Bus, DigitAI, require, nn_load_model, nn_reference

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'NNET')
ai = DigitAI(bus, slot=1)
check('network engine answers', ai.r(1023) == 0x4E4E4554)

# 1. random weights and pictures: every score and every hidden value must equal the math
rs = np.random.RandomState(16)
for shift, name in ((12, 'random network'), (8, 'random network that hits the 255 limit')):
    rnd = {'hid': 64, 'shift': shift, 'w1': rs.randint(-127, 128, (64, 784)).astype(np.int8),
           'b1': rs.randint(-100000, 100000, 64), 'w2': rs.randint(-127, 128, (10, 64)).astype(np.int8),
           'b2': rs.randint(-20000, 20000, 10)}
    ai.load(rnd)
    good = 0
    for _ in range(20):
        x = rs.randint(0, 256, 784).astype(np.uint8)
        d = ai.run(x)
        rd, rsc, rh = nn_reference(rnd, x)
        good += d == rd and ai.scores() == rsc and ai.hidden() == rh
    check('%s: 20 pictures = the math, to the bit' % name, good == 20, '%d of 20' % good)

# 2. the trained network
m = nn_load_model(nn_model)
t0 = time.time()
ai.load(m)
check('the trained network loads', True, '%.2f s for 50 KB' % (time.time() - t0))
same = right = 0
for x, want in zip(m['test'], m['labels']):
    d = ai.run(x)
    same += d == nn_reference(m, x)[0] and ai.scores() == nn_reference(m, x)[1]
    right += d == want
check('50 test digits: the FPGA = the math', same == 50, '%d of 50' % same)
check('50 test digits: at least 48 read right', right >= 48, '%d of 50 right' % right)
blank = ai.run(np.zeros(784, np.uint8))
check('an empty picture gives an answer too', 0 <= blank <= 9, 'reads %d' % blank)

# 3. speed
check('one digit takes 963 clocks (9.6 microseconds)', ai.cycles() == 963, '%d clocks' % ai.cycles())
c0 = ai.count()
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    ai.run(m['test'][n % 50]); n += 1
check('digits per second with Python sending the pictures', n > 200, '%d per second' % n)
check('the counter counts every digit', ai.count() - c0 == n, '%d' % (ai.count() - c0))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
