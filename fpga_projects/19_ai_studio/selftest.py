# 19 AI Studio self-test: the DDR engine against the Python integer math, bit for bit, for the three big
# networks in the DDR at once; the reader's test digits; the speed and how long it waits for the DDR.
import time
import numpy as np
import reader_big, writer_big, drawer_big
from blocks import Bus, MLPDDR, DDRStore, require, mlp_reference
from nn_train import load_layers, load_array

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'AIST')
MHZ = bus.rd(0, 6) / 1e6 or 100.0               # the design's clock (AI Studio runs at 75 MHz)
ports = bus.rd(1, 11) or 4                     # how many HP ports the engine uses (2 or 4)
store = DDRStore(region=(16 // ports) << 20, ports=ports)
nn = MLPDDR(bus, slot=1, store=store)
check('DDR network engine answers', nn.r(1023) == 0x4D4C5032)
check('16 MB of locked memory, physical pages found', len(store.pages) == 4096, '%d pages' % len(store.pages))
nets = {'reader': load_layers(reader_big), 'text model': load_layers(writer_big), 'drawer': load_layers(drawer_big)}
t0 = time.time()
handles = {k: nn.load(v) for k, v in nets.items()}
nn.ready()
check('three networks in the DDR', True, '%.1f MB, %.1f s' % (store.next * ports / 1e6, time.time() - t0))
rs = np.random.RandomState(19)
for name, layers in nets.items():
    nn.use(handles[name])
    good = 0
    for _ in range(10):
        x = rs.randint(0, 256, layers[0]['w'].shape[1]).astype(np.uint8)
        d, out = nn.run(x)
        ref = mlp_reference(layers, x)
        good += [int(v) for v in out] == ref[1] and (ref[0] is None or d == ref[0])
    check('%s: 10 inputs = the math, to the bit' % name, good == 10, '%d of 10; %d clocks, %d waiting for the DDR'
          % (good, nn.cycles(), nn.stalls()))
check('no read errors from the DDR', nn.r(7) == 0, '%d' % nn.r(7))
test, labels = load_array(reader_big, 'TEST'), reader_big.TEST_LABELS
nn.use(handles['reader'])
right = sum(nn.run(x)[0] == y for x, y in zip(test, labels))
check('the reader: 50 test digits', right >= 48, '%d of 50 right' % right)
emb = load_array(writer_big, 'EMBED')
nn.use(handles['text model'])
x = emb[[writer_big.VOCAB.index(c) for c in ('the fpga reads the pins of the board and ' * 2)[:writer_big.CTX]]].ravel()
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    nn.run(x); n += 1
check('text model: letters per second', n > 50, '%d per second, %.0f microseconds each in the FPGA' % (n, nn.cycles() / MHZ))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
