"""Shared PC-side tools for the Ardzy AI projects: train a stack of fully connected layers with numpy, and turn
it into the integers the FPGA's network engines use (8-bit weights, 32-bit sums, bytes between layers).

    P = train_mlp(X, Y, [784, 512, 256, 10], epochs=20)            # X: inputs as floats, Y: class numbers
    layers, scale = quantize_mlp(P, X_bytes, in_scale=255, act_last=0)

The integer math is mlp_reference() in blocks.py, exactly what the engine computes.
"""
import math
import numpy as np


def he(rs, a, b):
    return (rs.randn(a, b) * math.sqrt(2 / a)).astype(np.float32)


class Adam:
    def __init__(self, P, lr=2e-3):
        self.P, self.lr, self.t = P, lr, 0
        self.M = {k: np.zeros_like(v) for k, v in P.items()}
        self.S = {k: np.zeros_like(v) for k, v in P.items()}

    def step(self, G, lr=None, decay=1e-5):
        self.t += 1
        lr = self.lr if lr is None else lr
        for k, g in G.items():
            if k[0] == 'W':
                g = g + decay * self.P[k]
            self.M[k] = .9 * self.M[k] + .1 * g
            self.S[k] = .999 * self.S[k] + .001 * g * g
            self.P[k] -= lr * (self.M[k] / (1 - .9 ** self.t)) / (np.sqrt(self.S[k] / (1 - .999 ** self.t)) + 1e-8)


def mlp_forward(P, x, n, rs=None, drop=0.0):
    """Hidden layers ReLU (with dropout while training), the last one raw scores. Returns (scores, cache)."""
    acts, masks, pre = [x], [], []
    h = x
    for i in range(n):
        a = h @ P['W%d' % i] + P['b%d' % i]
        pre.append(a)
        if i < n - 1:
            h = np.maximum(a, 0)
            if rs is not None and drop:
                m = (rs.rand(*h.shape) > drop).astype(np.float32) / (1 - drop)
                h = h * m
                masks.append(m)
            else:
                masks.append(None)
            acts.append(h)
        else:
            h = a
    return h, (acts, masks, pre)


def mlp_backward(P, n, dz, cache):
    """Gradients of all layers for d(loss)/d(scores) = dz. Also returns d(loss)/d(input)."""
    acts, masks, pre = cache
    G = {}
    d = dz
    for i in range(n - 1, -1, -1):
        G['W%d' % i] = acts[i].T @ d
        G['b%d' % i] = d.sum(0)
        d = d @ P['W%d' % i].T
        if i > 0:
            if masks[i - 1] is not None:
                d = d * masks[i - 1]
            d = d * (pre[i - 1] > 0)
    return G, d


def train_mlp(X, Y, sizes, epochs=20, batch=128, lr=2e-3, drop=0.15, seed=1, Xv=None, Yv=None, prepare=None, log=print):
    """Train a classifier. X: (N, in) float32 (or uint8 with prepare = a function turning a batch into floats)."""
    rs = np.random.RandomState(seed)
    n = len(sizes) - 1
    P = {}
    for i in range(n):
        P['W%d' % i] = he(rs, sizes[i], sizes[i + 1])
        P['b%d' % i] = np.zeros(sizes[i + 1], np.float32)
    opt = Adam(P, lr)
    prep = prepare or (lambda b, r: b.astype(np.float32))
    for ep in range(epochs):
        cur = lr * .5 * (1 + math.cos(math.pi * ep / epochs))
        order = rs.permutation(len(X))
        for s in range(0, len(X), batch):
            b = order[s:s + batch]
            x = prep(X[b], rs)
            z, cache = mlp_forward(P, x, n, rs, drop)
            z = z - z.max(1, keepdims=True)
            p = np.exp(z); p /= p.sum(1, keepdims=True)
            p[np.arange(len(b)), Y[b]] -= 1
            G, _ = mlp_backward(P, n, p / len(b), cache)
            opt.step(G, cur)
        if Xv is not None:
            z, _ = mlp_forward(P, prep(Xv, None), n)
            log('  round %2d: %.2f %% right on data it never saw' % (ep + 1, 100 * (z.argmax(1) == Yv).mean()))
    return P


def _shift_for(acc):
    pos = acc[acc > 0]
    top = np.percentile(pos, 99.9) if len(pos) else 255
    return max(0, int(math.ceil(math.log2(max(top, 1) / 255))))


def quantize_mlp(P, Xb, k_in, offset=0, last='scores', sample=6000):
    """Floats -> engine integers. Xb: example inputs as the engine gets them (bytes). The input byte means
    float * k_in + offset (offset 128 for signed inputs; it is taken back out through the first biases).
    last = 'scores' (act 0) or 'sigmoid' (act 2: pixels, needs the score * 16 before the table).
    Returns (layers, scale): for 'scores', float score = integer score * scale."""
    n = len([k for k in P if k[0] == 'W'])
    x = np.asarray(Xb[:sample], np.int64)
    layers, k = [], k_in
    for i in range(n):
        W, b = P['W%d' % i], P['b%d' % i]
        last_layer = i == n - 1
        if last_layer and last == 'sigmoid':
            # the table wants (score >> shift) = 16 x the float score: choose shift and weight scale together
            wmax = np.abs(W).max()
            sh = int(math.floor(math.log2(k * 127 / (16 * wmax))))
            if sh < 0:
                raise ValueError('the hidden values are too small for the sigmoid layer: use a smaller shift before')
            s = k / (16 * 2 ** sh)
        else:
            s = np.abs(W).max() / 127
        Wq = np.clip(np.round(W / s), -127, 127).astype(np.int64)            # (in, out)
        bq = np.round(b * k / s).astype(np.int64)
        if i == 0 and np.any(offset):           # offset: one number, or one per input
            bq = bq - (np.asarray(offset, np.int64) @ Wq if np.ndim(offset) else offset * Wq.sum(0))
        acc = x @ Wq + bq
        if last_layer:
            if last == 'sigmoid':
                layers.append({'w': Wq.T.astype(np.int8), 'b': bq, 'shift': sh, 'act': 2})
                return layers, None
            layers.append({'w': Wq.T.astype(np.int8), 'b': bq, 'shift': 0, 'act': 0})
            return layers, float(s / k)
        sh = _shift_for(acc)
        layers.append({'w': Wq.T.astype(np.int8), 'b': bq, 'shift': sh, 'act': 1})
        x = np.clip(acc >> sh, 0, 255)
        k = k / s / 2 ** sh
    return layers, None


def save_layers(path, layers, header, extra=None):
    """Write a model as a Python file the board can import (base64 weights)."""
    import base64
    L = ['# Generated: %s (do not edit; run the make_ script again).' % header]
    for name, v in (extra or {}).items():
        if isinstance(v, np.ndarray):
            s = base64.b64encode(np.ascontiguousarray(v).tobytes()).decode()
            L.append('%s_DTYPE = %r' % (name, str(v.dtype)))
            L.append('%s_SHAPE = %r' % (name, list(v.shape)))
            L.append('%s = (' % name)
            L += ["    '%s'" % s[i:i + 100] for i in range(0, len(s), 100)]
            L.append(')')
        else:
            if isinstance(v, np.generic):                     # numpy numbers as plain Python numbers
                v = v.item()
            L.append('%s = %r' % (name, v))
    L.append('SHAPES = %r' % [list(l['w'].shape) for l in layers])
    L.append('SHIFTS = %r' % [l['shift'] for l in layers])
    L.append('ACTS = %r' % [l['act'] for l in layers])
    for k, l in enumerate(layers):
        L.append('B%d = %r' % (k + 1, [int(v) for v in l['b']]))
        s = base64.b64encode(np.ascontiguousarray(l['w']).tobytes()).decode()
        L.append('W%d = (' % (k + 1))
        L += ["    '%s'" % s[i:i + 100] for i in range(0, len(s), 100)]
        L.append(')')
    open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')


def load_layers(mod):
    """The layers of a model file written by save_layers (works on the board too)."""
    import base64
    dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), dtype=np.int8).reshape(shape)
    return [{'w': dec(getattr(mod, 'W%d' % (k + 1)), mod.SHAPES[k]), 'b': getattr(mod, 'B%d' % (k + 1)),
             'shift': mod.SHIFTS[k], 'act': mod.ACTS[k]} for k in range(len(mod.SHAPES))]


def load_array(mod, name):
    import base64
    return np.frombuffer(base64.b64decode(''.join(getattr(mod, name))), dtype=getattr(mod, name + '_DTYPE')).reshape(
        getattr(mod, name + '_SHAPE'))
