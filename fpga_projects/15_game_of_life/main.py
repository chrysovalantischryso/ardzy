# 15 Game of Life demo: famous patterns in the Monitor, then the speed race against Python.
import time
from blocks import Bus, Life, life_step, require

bus = Bus()
require(bus, 'LIFE')
life = Life(bus, slot=1)


def show(title, gens=None):
    g = life.read()
    print('\n%s  (generation %d, %d live cells)' % (title, life.generation(), sum(bin(x).count('1') for x in g)))
    print(Life.text(g, rows=32))


life.clear()
life.place('glider', 2, 2)
life.place('lwss', 12, 2)
life.place('pulsar', 2, 40)
life.place('beacon', 22, 30)
life.place('blinker', 26, 50)
show('Still lifes, oscillators and spaceships')
for i in range(3):
    life.steps(4)
    show('4 generations later: the glider and the spaceship move, the others blink')

print('\nThe race: 100 generations of a random grid')
life.randomize()
g = life.read()
t = time.time()
for _ in range(100):
    g = life_step(g)
py = time.time() - t
t = time.time()
life.steps(100)
fpga = time.time() - t
print('   Python on the ARM: %.2f s;  FPGA: %.4f s (most of it is Python asking the FPGA if it is done)' % (py, fpga))
print('   same result: %s' % (life.read() == g))
life.run()
time.sleep(1.2)
print('   flat out the FPGA does %d generations per second' % life.per_second())
life.stop()

print('\nThe Gosper glider gun shoots a new glider every 30 generations (watch for 10 frames)')
life.clear()
life.place('gosper_gun', 1, 1)
for i in range(10):
    life.steps(30)
    show('Gun, frame %d' % (i + 1))

print('\nNow random soup for ever, 10 generations per second (stop the program to stop)')
life.randomize()
while True:
    life.steps(1)
    if life.generation() % 10 == 0:
        show('Soup')
    time.sleep(0.1)
