# 17 Text AI self-test: the general network engine against the Python integer math, bit for bit, and the speed.
import base64, time
import numpy as np
import text_model as tm
from blocks import Bus, MLP, require, mlp_reference

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'TEXT')
nn = MLP(bus, slot=1)
check('network engine answers', nn.r(1023) == 0x4D4C5031)

rs = np.random.RandomState(17)
rnd = lambda sizes, acts, shifts: [{'w': rs.randint(-127, 128, (sizes[k + 1], sizes[k])).astype(np.int8),
                                    'b': rs.randint(-30000, 30000, sizes[k + 1]), 'shift': shifts[k], 'act': a}
                                   for k, a in enumerate(acts)]
nets = [('ReLU then sigmoid', rnd([40, 48, 30], [1, 2], [10, 9])), ('three layers, scores', rnd([100, 64, 32, 20], [1, 1, 0], [11, 9, 0]))]
handles = [nn.load(l) for _, l in nets]
for (name, layers), h in zip(nets, handles):
    nn.use(h)
    good = 0
    for _ in range(20):
        x = rs.randint(0, 256, layers[0]['w'].shape[1]).astype(np.uint8)
        hw = nn.run(x)
        ref = mlp_reference(layers, x)
        good += (hw[0] == ref[0] if ref[0] is not None else True) and [int(v) for v in hw[1]] == ref[1]
    check('%s: 20 inputs = the math, to the bit' % name, good == 20, '%d of 20' % good)

nn = MLP(bus, slot=1)                       # the text model alone
dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), dtype=np.int8).reshape(shape)
layers = [{'w': dec(getattr(tm, 'W%d' % (k + 1)), tm.SHAPES[k]), 'b': getattr(tm, 'B%d' % (k + 1)),
           'shift': tm.SHIFTS[k], 'act': tm.ACTS[k]} for k in range(3)]
emb = np.frombuffer(base64.b64decode(''.join(tm.EMBED)), dtype=np.uint8).reshape(len(tm.VOCAB), -1)
t0 = time.time()
nn.use(nn.load(layers))
check('the text model loads', True, '%.2f s for %d KB' % (time.time() - t0, sum(l['w'].size for l in layers) // 1024))
text = 'the board has an fpga and two arm cores that run linux, and the program can talk to the fpga'
same = right = 0
for k in range(40):
    ids = [tm.VOCAB.index(c) for c in text[k:k + 16]]
    d, s = nn.run(emb[ids].ravel())
    same += (d, [int(v) for v in s]) == mlp_reference(layers, emb[ids].ravel())
    right += tm.VOCAB[d] == text[k + 16]
check('40 next-letter guesses: the FPGA = the math', same == 40, '%d of 40' % same)
check('it guesses many next letters right', right >= 18, '%d of 40 right' % right)
check('one letter takes about 2100 clocks', 1900 < nn.cycles() < 2300, '%d clocks = %.1f us' % (nn.cycles(), nn.cycles() / 100))
n, t0 = 0, time.time()
while time.time() - t0 < 1.0:
    nn.run(emb[ids].ravel()); n += 1
check('letters per second with Python around it', n > 100, '%d per second' % n)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
