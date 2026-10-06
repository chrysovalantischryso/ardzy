# 15 Game of Life self-test: the FPGA's generations against the Python rules, famous patterns, the speed.
import random
import time
from blocks import Bus, Life, life_step, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'LIFE')
life = Life(bus, slot=1)
check('life engine answers', life.r(1023) == 0x4C494645)

random.seed(15)
life.stop()
g = [random.getrandbits(64) for _ in range(64)]
life.write(g)
check('a grid written comes back the same', life.read() == g)
life.steps(1)
g1 = life_step(g)
check('1 generation = the rules', life.read() == g1)
check('population = live cells', life.population() == sum(bin(x).count('1') for x in g1), str(life.population()))
life.steps(20)
for _ in range(20):
    g1 = life_step(g1)
check('21 generations = the rules', life.read() == g1 and life.generation() == 21, 'generation %d' % life.generation())

life.clear()
life.place('blinker', 10, 10)
a = life.read()
life.steps(1)
b = life.read()
life.steps(1)
check('a blinker: period 2', a != b and life.read() == a)

life.clear()
life.place('glider', 0, 0)
start = life.read()
life.steps(256)
check('a glider flies once around the torus in 256 generations', life.read() == start)

life.randomize()
pop = sum(bin(x).count('1') for x in life.read())
check('random fill: about half the cells alive', 1700 < pop < 2400, '%d of 4096' % pop)
life.randomize(sparse=True)
pop = sum(bin(x).count('1') for x in life.read())
check('sparse fill: about a quarter', 800 < pop < 1250, '%d of 4096' % pop)

life.run()
time.sleep(2.1)
n = life.per_second()
life.stop()
check('speed: about 1.43 million generations per second', abs(n - 100e6 / 70) < 2000, '%d per second' % n)
life.run(per_second=1000)
time.sleep(2.1)
n = life.per_second()
life.stop()
check('slowed down to 1000 per second', abs(n - 1000) <= 2, '%d per second' % n)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
