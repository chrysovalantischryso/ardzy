"""Simulation test of project 18 in the network engine (mlp_engine.v) with Icarus Verilog (PC only).

    python sim/run_sim.py

The drawer and project 16's reader are loaded together, as on the board; drawings and readings must equal
mlp_reference() in blocks.py, to the bit.
"""
import base64, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
from mlp_sim import Sim                       # noqa: E402
from blocks import nn_load_model              # noqa: E402
import image_model as im                      # noqa: E402
import reader_model                           # noqa: E402

ok = []


def check(name, cond, detail=''):
    ok.append(cond)
    print('%-4s %-50s %s' % ('ok' if cond else 'FAIL', name, detail))


def main():
    dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), dtype=np.int8).reshape(shape)
    drawer = [{'w': dec(getattr(im, 'W%d' % (k + 1)), im.SHAPES[k]), 'b': getattr(im, 'B%d' % (k + 1)),
               'shift': im.SHIFTS[k], 'act': im.ACTS[k]} for k in range(2)]
    r = nn_load_model(reader_model)
    reader = [{'w': r['w1'], 'b': r['b1'], 'shift': r['shift'], 'act': 1}, {'w': r['w2'], 'b': r['b2'], 'shift': 0, 'act': 0}]
    sim = Sim()
    hd, hr = sim.load(drawer), sim.load(reader)
    rs = np.random.RandomState(18)
    for k in range(4):
        z = np.clip(np.round(rs.randn(im.Z) * im.ZSCALE) + 128, 0, 255)
        y = np.zeros(10); y[(3 * k) % 10] = im.ZSCALE
        sim.run('draw#%d' % k, hd, drawer, np.concatenate([z, y]).astype(np.uint8))
    for k in range(3):
        sim.run('read#%d' % k, hr, reader, r['test'][k * 11])
    sim.finish([os.path.join(HERE, '..', '..', 'common', f) for f in ('mlp_engine.v', 'mlp_sigmoid.v')], check)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))


if __name__ == '__main__':
    main()
