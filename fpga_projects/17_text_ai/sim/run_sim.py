"""Simulation test of the network engine (mlp_engine.v) with Icarus Verilog (PC only).

    python sim/run_sim.py

Random networks of every kind (1 to 3 layers; ReLU, sigmoid, scores), two networks in the engine at once,
and the trained text model: every output must equal mlp_reference() in blocks.py, to the bit.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
sys.path.insert(0, os.path.join(HERE, '..'))
from mlp_sim import Sim, random_layers           # noqa: E402

ok = []


def check(name, cond, detail=''):
    ok.append(cond)
    print('%-4s %-50s %s' % ('ok' if cond else 'FAIL', name, detail))


def main():
    rs = np.random.RandomState(17)
    sim = Sim()
    nets = [('relu-sigmoid', random_layers(rs, [40, 48, 30], [1, 2], [10, 9])),
            ('relu-relu-scores', random_layers(rs, [100, 64, 32, 20], [1, 1, 0], [11, 9, 0])),
            ('one layer', random_layers(rs, [8, 16], [0], [0]))]
    loaded = [(name, sim.load(layers), layers) for name, layers in nets]
    for name, cfg, layers in loaded + loaded[:1]:            # the first one again: switching back works
        for k in range(2):
            x = rs.randint(0, 256, layers[0]['w'].shape[1]).astype(np.uint8)
            sim.run('%s#%d' % (name.replace(' ', '_'), len(sim.cases)), cfg, layers, x)
    try:
        import text_model as tm
        from blocks import MLP
        lay = [{'w': np.frombuffer(__import__('base64').b64decode(''.join(getattr(tm, 'W%d' % (k + 1)))), np.int8).reshape(tm.SHAPES[k]),
                'b': getattr(tm, 'B%d' % (k + 1)), 'shift': tm.SHIFTS[k], 'act': tm.ACTS[k]} for k in range(3)]
        sim2 = sim
        sim2.mlp.wnext = sim2.mlp.bnext = 0                     # the text model fills the engine alone
        cfg = sim2.load(lay)
        emb = np.frombuffer(__import__('base64').b64decode(''.join(tm.EMBED)), np.uint8).reshape(len(tm.VOCAB), -1)
        text = 'the fpga reads the pins of the board'
        for k in range(3):
            ids = [tm.VOCAB.index(c) for c in text[k * 5:k * 5 + 16]]
            sim2.run('text#%d' % k, cfg, lay, emb[ids].ravel())
    except ImportError:
        print('(no text_model.py yet: only the random networks)')
    sim.finish([os.path.join(HERE, '..', '..', 'common', f) for f in ('mlp_engine.v', 'mlp_sigmoid.v')], check)
    print('RESULT: %d of %d ok' % (sum(ok), len(ok)))


if __name__ == '__main__':
    main()
