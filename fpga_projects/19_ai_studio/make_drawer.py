"""19 AI Studio: train the big digit drawer, write drawer_big.py (PC, about 20 minutes).

    python make_drawer.py

The same idea as project 18 (a conditional VAE), bigger:
    encoder (training only): 784 pixels + the digit -> 512 -> 16 style numbers (mean and spread)
    decoder (the drawer):    16 style numbers + the digit -> 256 -> 512 -> 784 pixels (sigmoid)
The decoder has 540 000 weights (project 18's has 78 000); the AI Studio engine streams it from the DDR.
"""
import math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '16_digit_ai'))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))
from nn_train import he, Adam, mlp_forward, mlp_backward, quantize_mlp, save_layers   # noqa: E402
from blocks import mlp_reference                                                       # noqa: E402

Z, ZSCALE = 16, 32
ENC, DEC = [794, 512, 2 * Z], [Z + 10, 256, 512, 784]


def init(rs, sizes):
    P = {}
    for i in range(len(sizes) - 1):
        P['W%d' % i] = he(rs, sizes[i], sizes[i + 1])
        P['b%d' % i] = np.zeros(sizes[i + 1], np.float32)
    return P


def train(X, Y, epochs=30, seed=19):
    rs = np.random.RandomState(seed)
    Pe, Pd = init(rs, ENC), init(rs, DEC)
    Pe['W1'] *= .1
    oe, od = Adam(Pe, 1.5e-3), Adam(Pd, 1.5e-3)
    Xf = X.astype(np.float32) / 255
    oh = np.eye(10, dtype=np.float32)[Y]
    for ep in range(epochs):
        lr = 1.5e-3 * .5 * (1 + math.cos(math.pi * ep / epochs))
        idx = rs.permutation(len(X))
        tot = klt = 0
        for s in range(0, len(X), 128):
            b = idx[s:s + 128]; n = len(b)
            x, y = Xf[b], oh[b]
            eo, ec = mlp_forward(Pe, np.concatenate([x, y], 1), 2)
            mu, lv = eo[:, :Z], np.clip(eo[:, Z:], -8, 8)
            eps = rs.randn(n, Z).astype(np.float32)
            z = mu + np.exp(.5 * lv) * eps
            lo, dc = mlp_forward(Pd, np.concatenate([z, y], 1), 3)
            xr = 1 / (1 + np.exp(-lo))
            tot += -(x * np.log(xr + 1e-7) + (1 - x) * np.log(1 - xr + 1e-7)).sum(1).mean() * n
            klt += (-.5 * (1 + lv - mu ** 2 - np.exp(lv))).sum(1).mean() * n
            Gd, din = mlp_backward(Pd, 3, (xr - x) / n, dc)
            dz = din[:, :Z]
            dmu = dz + mu / n
            dlv = dz * eps * .5 * np.exp(.5 * lv) + .5 * (np.exp(lv) - 1) / n
            Ge, _ = mlp_backward(Pe, 2, np.concatenate([dmu, dlv], 1), ec)
            od.step(Gd, lr, 0); oe.step(Ge, lr, 0)
        print('  round %2d: drawing error %.1f, style spread %.1f' % (ep + 1, tot / len(X), klt / len(X)), flush=True)
    return Pd


def drawer_input(digit, z):
    zb = np.clip(np.round(np.asarray(z) * ZSCALE) + 128, 0, 255)
    y = np.zeros(10); y[digit] = ZSCALE
    return np.concatenate([zb, y]).astype(np.uint8)


def main():
    t0 = time.time()
    import make_model as dm
    X, Y = dm.make_set(dm.usable_fonts(), 35000, 35000, 21)
    print('made %d training digits in %.0f s' % (len(X), time.time() - t0), flush=True)
    Pd = train(X, Y)
    rs = np.random.RandomState(3)
    ex = np.array([drawer_input(rs.randint(10), rs.randn(Z)) for _ in range(4000)])
    layers, _ = quantize_mlp(Pd, ex, k_in=ZSCALE, offset=[128] * Z + [0] * 10, last='sigmoid')
    # check with the big reader if it is there, else with project 16's
    try:
        import reader_big as rm
        from nn_train import load_layers
        reader = load_layers(rm)
    except ImportError:
        sys.path.insert(0, os.path.join(HERE, '..', '16_digit_ai'))
        import nn_model
        from blocks import nn_load_model
        r = nn_load_model(nn_model)
        reader = [{'w': r['w1'], 'b': r['b1'], 'shift': r['shift'], 'act': 1}, {'w': r['w2'], 'b': r['b2'], 'shift': 0, 'act': 0}]
    right = 0
    for k in range(500):
        d = k % 10
        _, pix = mlp_reference(layers, drawer_input(d, rs.randn(Z)))
        right += mlp_reference(reader, np.array(pix, np.uint8))[0] == d
    print('the reader reads %.1f %% of 500 new drawings as the digit asked for (shifts %s)' % (100 * right / 500, [l['shift'] for l in layers]))
    save_layers(os.path.join(HERE, 'drawer_big.py'), layers, 'the big digit drawer %s, %.1f %% of its drawings read right' % (DEC, 100 * right / 500),
                {'Z': Z, 'ZSCALE': ZSCALE})
    print('wrote drawer_big.py in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
