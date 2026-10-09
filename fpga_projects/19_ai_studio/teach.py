"""19 AI Studio: teach the big reader YOUR handwriting (runs on the PC; the Ardzy app calls teach()).

Your drawings (28 x 28, with the right digit) come from the app's Read tab. The reader is fine-tuned on them a
few rounds; mixed in are 3000 practice digits from the drawer network (so it does not forget the other ways to
write a digit). The result is a new reader_mine.py, in the engine's integers, for the board.

The reader is stored as integers only. A float network that computes the same thing is made from them:
layer weights W / 2^SHIFT and biases B / 2^SHIFT, the inputs stay bytes 0 .. 255; that one is trained, then
turned back into integers.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nn_train import Adam, mlp_forward, mlp_backward, quantize_mlp, save_layers, load_layers, load_array   # noqa: E402
from blocks import mlp_reference                                                                         # noqa: E402


def augment(x, rs):
    """A drawing moved by up to 2 pixels."""
    img = x.reshape(28, 28)
    dy, dx = rs.randint(-2, 3), rs.randint(-2, 3)
    return np.roll(np.roll(img, dy, 0), dx, 1).ravel()


def practice_digits(n, seed=7):
    import drawer_big
    L = load_layers(drawer_big)
    rs = np.random.RandomState(seed)
    X, Y = [], []
    for k in range(n):
        d = k % 10
        z = np.clip(np.round(rs.randn(drawer_big.Z) * drawer_big.ZSCALE) + 128, 0, 255)
        y = np.zeros(10); y[d] = drawer_big.ZSCALE
        _, pix = mlp_reference(L, np.concatenate([z, y]).astype(np.uint8))
        X.append(pix); Y.append(d)
    return np.array(X, np.uint8), np.array(Y)


def teach(samples, out_path, log=print, rounds=12, base='reader_big'):
    """samples: [(784 pixels 0..255, digit)]. Writes the new reader to out_path. Returns a short report."""
    import importlib
    mod = importlib.import_module(base)
    L = load_layers(mod)
    n = len(L)
    P = {}
    for i, l in enumerate(L):                    # the integer network as floats (same results, without rounding)
        P['W%d' % i] = (l['w'].astype(np.float32).T / 2 ** l['shift'])
        P['b%d' % i] = (np.asarray(l['b'], np.float32) / 2 ** l['shift'])
    scale = mod.SCALE
    Xu = np.array([s[0] for s in samples], np.uint8)
    Yu = np.array([s[1] for s in samples])
    before = sum(mlp_reference(L, x)[0] == y for x, y in zip(Xu, Yu))
    log('Your %d drawings: the reader gets %d right now. Making 3000 practice digits with the drawer ...' % (len(Yu), before))
    Xp, Yp = practice_digits(3000)
    rs = np.random.RandomState(3)
    opt = Adam(P, 2e-4)
    for r in range(rounds):
        Xb = np.concatenate([np.array([augment(x, rs) for x in np.repeat(Xu, 20, 0)]), Xp])
        Yb = np.concatenate([np.repeat(Yu, 20), Yp])
        order = rs.permutation(len(Yb))
        for s in range(0, len(order), 128):
            b = order[s:s + 128]
            z, cache = mlp_forward(P, Xb[b].astype(np.float32), n)
            z = z * scale
            z -= z.max(1, keepdims=True)
            p = np.exp(z); p /= p.sum(1, keepdims=True)
            p[np.arange(len(b)), Yb[b]] -= 1
            G, _ = mlp_backward(P, n, p * scale / len(b), cache)
            opt.step(G, 2e-4 * (1 - r / rounds), 0)
        log('  round %d of %d' % (r + 1, rounds))
    Xq = np.concatenate([Xu, Xp])
    layers, sc = quantize_mlp(P, Xq, k_in=1)
    after = sum(mlp_reference(layers, x)[0] == y for x, y in zip(Xu, Yu))
    kept = sum(mlp_reference(layers, x)[0] == y for x, y in zip(Xp[:1000], Yp[:1000]))
    test = load_array(mod, 'TEST') if hasattr(mod, 'TEST') else None
    extra = {'SCALE': sc, 'ACCURACY': float(after) / len(Yu), 'MINE': len(Yu)}
    if test is not None:
        extra.update({'TEST': test, 'TEST_LABELS': list(mod.TEST_LABELS)})
    save_layers(out_path, layers, 'the big reader, taught %d of your drawings' % len(Yu), extra)
    report = 'Your drawings: %d of %d right before, %d after. Practice digits still right: %d of 1000.' % (before, len(Yu), after, kept)
    log(report)
    return report
