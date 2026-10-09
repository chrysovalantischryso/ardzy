# 18 Image AI self-test: the drawer and the reader in the FPGA against the Python integer math, and what it draws.
import base64, time
import numpy as np
import image_model as im
import reader_model
from blocks import Bus, MLP, require, mlp_reference, nn_load_model

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'DRAW')
nn = MLP(bus, slot=1)
check('network engine answers', nn.r(1023) == 0x4D4C5031)
dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), dtype=np.int8).reshape(shape)
drawer = [{'w': dec(getattr(im, 'W%d' % (k + 1)), im.SHAPES[k]), 'b': getattr(im, 'B%d' % (k + 1)),
           'shift': im.SHIFTS[k], 'act': im.ACTS[k]} for k in range(2)]
r = nn_load_model(reader_model)
reader = [{'w': r['w1'], 'b': r['b1'], 'shift': r['shift'], 'act': 1}, {'w': r['w2'], 'b': r['b2'], 'shift': 0, 'act': 0}]
t0 = time.time()
hd, hr = nn.load(drawer), nn.load(reader)
check('both networks fit and load', True, '%.2f s, %d of 2048 words per lane used' % (time.time() - t0, nn.wnext))


def inp(d, z):
    zb = np.clip(np.round(z * im.ZSCALE) + 128, 0, 255)
    y = np.zeros(10); y[d] = im.ZSCALE
    return np.concatenate([zb, y]).astype(np.uint8)


rs = np.random.RandomState(18)
same = right = rsame = 0
for k in range(30):
    d = k % 10
    x = inp(d, rs.randn(im.Z))
    nn.use(hd)
    pix = [int(v) for v in nn.run(x)[1]]
    same += pix == mlp_reference(drawer, x)[1]
    nn.use(hr)
    got, s = nn.run(np.array(pix, np.uint8))
    rsame += (got, [int(v) for v in s]) == mlp_reference(reader, np.array(pix, np.uint8))
    right += got == d
check('30 drawings: every pixel = the math', same == 30, '%d of 30' % same)
check('30 readings: every score = the math', rsame == 30, '%d of 30' % rsame)
check('the reader recognises most drawings', right >= 24, '%d of 30 read as the digit asked for' % right)
nn.use(hd)
nn.run(inp(3, np.zeros(im.Z)))
check('one drawing takes about 1300 clocks', 1100 < nn.cycles() < 1500, '%d clocks = %.1f us' % (nn.cycles(), nn.cycles() / 100))
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    nn.run(inp(n % 10, rs.randn(im.Z))); n += 1
check('drawings per second with Python around it', n > 50, '%d per second' % n)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
