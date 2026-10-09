"""18 Image AI: train a network that draws new handwritten digits, write image_model.py (PC).

    python make_model.py            (about 4 minutes; numpy and Pillow, Windows fonts for the training digits)

It is a "conditional variational autoencoder" (CVAE). Training uses two halves:
  * the encoder looks at a digit and squeezes it into 16 numbers (its "style": slant, thickness, size ...)
  * the decoder gets those 16 numbers plus WHICH digit it should be, and draws the 28 x 28 picture back.
Both learn together: the drawing must look like the original, and the 16 numbers must stay close to
ordinary random numbers. After training only the decoder is kept: give it 16 random numbers and a digit,
and it draws a new one, never the same twice.

    16 random numbers + the digit (10 inputs) -> 96 neurons (ReLU) -> 784 pixels (sigmoid)

The decoder runs in the FPGA's network engine (mlp_engine.v, 76 000 weights). Next to it the engine
holds project 16's digit reader, so the FPGA can check what it drew.
"""
import base64, math, os, random, shutil, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '16_digit_ai'))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))     # (before 16's own copy of blocks.py)
from blocks import mlp_reference                      # noqa: E402

Z, HID, EH = 16, 96, 256
SEED = 18
ZSCALE = 32             # the decoder's input bytes: z * 32 + 128 for the 16 numbers, 32 for the chosen digit


def train(X, Y, epochs=30):
    rs = np.random.RandomState(SEED)
    he = lambda a, b: (rs.randn(a, b) * math.sqrt(2 / a)).astype(np.float32)
    P = {'We': he(794, EH), 'be': np.zeros(EH, np.float32), 'Wm': he(EH, Z) * .1, 'bm': np.zeros(Z, np.float32),
         'Wv': he(EH, Z) * .1, 'bv': np.zeros(Z, np.float32),
         'Wd': he(Z + 10, HID), 'bd': np.zeros(HID, np.float32), 'Wo': he(HID, 784), 'bo': np.zeros(784, np.float32)}
    M = {k: np.zeros_like(v) for k, v in P.items()}
    S = {k: np.zeros_like(v) for k, v in P.items()}
    Xf = X.astype(np.float32) / 255
    oh = np.eye(10, dtype=np.float32)[Y]
    step = 0
    for ep in range(epochs):
        lr = 1.5e-3 * .5 * (1 + math.cos(math.pi * ep / epochs))
        idx = rs.permutation(len(X))
        tot = kl_tot = 0
        for s in range(0, len(X), 128):
            b = idx[s:s + 128]; n = len(b)
            x, y = Xf[b], oh[b]
            # encoder
            ein = np.concatenate([x, y], 1)
            ae = ein @ P['We'] + P['be']; he_ = np.maximum(ae, 0)
            mu = he_ @ P['Wm'] + P['bm']; lv = np.clip(he_ @ P['Wv'] + P['bv'], -8, 8)
            eps = rs.randn(n, Z).astype(np.float32)
            z = mu + np.exp(.5 * lv) * eps
            # decoder
            din = np.concatenate([z, y], 1)
            ad = din @ P['Wd'] + P['bd']; hd = np.maximum(ad, 0)
            lo = hd @ P['Wo'] + P['bo']
            xr = 1 / (1 + np.exp(-lo))
            bce = -(x * np.log(xr + 1e-7) + (1 - x) * np.log(1 - xr + 1e-7)).sum(1).mean()
            kl = (-.5 * (1 + lv - mu ** 2 - np.exp(lv))).sum(1).mean()
            tot += bce * n; kl_tot += kl * n
            # backwards
            dlo = (xr - x) / n
            G = {'Wo': hd.T @ dlo, 'bo': dlo.sum(0)}
            dad = (dlo @ P['Wo'].T) * (ad > 0)
            G['Wd'] = din.T @ dad; G['bd'] = dad.sum(0)
            dz = (dad @ P['Wd'].T)[:, :Z]
            dmu = dz + mu / n
            dlv = dz * eps * .5 * np.exp(.5 * lv) + .5 * (np.exp(lv) - 1) / n
            G['Wm'] = he_.T @ dmu; G['bm'] = dmu.sum(0)
            G['Wv'] = he_.T @ dlv; G['bv'] = dlv.sum(0)
            dhe = (dmu @ P['Wm'].T + dlv @ P['Wv'].T) * (ae > 0)
            G['We'] = ein.T @ dhe; G['be'] = dhe.sum(0)
            step += 1
            for k in P:
                M[k] = .9 * M[k] + .1 * G[k]; S[k] = .999 * S[k] + .001 * G[k] * G[k]
                P[k] -= lr * (M[k] / (1 - .9 ** step)) / (np.sqrt(S[k] / (1 - .999 ** step)) + 1e-8)
        print('  round %2d: drawing error %.1f, style spread %.1f' % (ep + 1, tot / len(X), kl_tot / len(X)), flush=True)
    return P


def quantize(P):
    """The decoder in the engine's integers. Input bytes: z * 32 + 128 (16 of them) and 32 for the chosen digit
    (0 for the others): both mean "value * 32", the +128 is taken back out through the biases."""
    W1 = P['Wd'] / ZSCALE                                   # per input byte
    s1 = np.abs(W1).max() / 127
    W1q = np.clip(np.round(W1 / s1), -127, 127).astype(np.int64)            # (26, HID)
    b1q = np.round(P['bd'] / s1).astype(np.int64) - 128 * W1q[:Z].sum(0)
    rs = np.random.RandomState(1)
    zz = np.clip(np.round(rs.randn(4000, Z) * ZSCALE) + 128, 0, 255)
    yy = np.eye(10)[rs.randint(0, 10, 4000)] * ZSCALE
    acc1 = np.concatenate([zz, yy], 1).astype(np.int64) @ W1q + b1q
    # the sigmoid table needs (pixel score * 16) after the second layer's shift: pick the shifts and scales so
    sh1 = max(0, int(math.ceil(math.log2(np.percentile(acc1[acc1 > 0], 99.9) / 255))))
    k1 = 1 / (s1 * 2 ** sh1)                                 # hidden integer = hidden float * k1
    wmax = np.abs(P['Wo']).max()
    sh2 = int(math.floor(math.log2(k1 * 127 / (16 * wmax))))
    while sh2 < 0:                                           # (not needed with normal weights)
        sh1 += 1; k1 /= 2; sh2 = int(math.floor(math.log2(k1 * 127 / (16 * wmax))))
    s2 = k1 / (16 * 2 ** sh2)
    W2q = np.clip(np.round(P['Wo'] / s2), -127, 127).astype(np.int64)
    b2q = np.round(P['bo'] * k1 / s2).astype(np.int64)
    return [{'w': W1q.T.astype(np.int8), 'b': b1q, 'shift': sh1, 'act': 1},
            {'w': W2q.T.astype(np.int8), 'b': b2q, 'shift': sh2, 'act': 2}]


def decoder_input(digit, z):
    zb = np.clip(np.round(np.asarray(z) * ZSCALE) + 128, 0, 255)
    y = np.zeros(10); y[digit] = ZSCALE
    return np.concatenate([zb, y]).astype(np.uint8)


def write_model(layers, info):
    b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
    L = ['# Generated by make_model.py: the trained digit drawer (do not edit; run make_model.py again).', '# ' + info,
         'Z = %d' % Z, 'ZSCALE = %d' % ZSCALE, 'SHIFTS = %r' % [l['shift'] for l in layers],
         'ACTS = %r' % [l['act'] for l in layers], 'SHAPES = %r' % [list(l['w'].shape) for l in layers]]
    for k, l in enumerate(layers):
        L.append('B%d = %r' % (k + 1, [int(v) for v in l['b']]))
    for k, l in enumerate(layers):
        s = b64(l['w'])
        L.append('W%d = (' % (k + 1))
        L += ["    '%s'" % s[i:i + 100] for i in range(0, len(s), 100)]
        L.append(')')
    open(os.path.join(HERE, 'image_model.py'), 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')


def main():
    t0 = time.time()
    import make_model as dm                                  # project 16's digit maker (fonts and pen strokes)
    from blocks import nn_load_model, nn_reference
    import nn_model
    fonts = dm.usable_fonts()
    X, Y = dm.make_set(fonts, 25000, 25000, SEED)
    print('made %d training digits in %.0f s' % (len(X), time.time() - t0), flush=True)
    P = train(X, Y)
    layers = quantize(P)
    reader = nn_load_model(nn_model)
    rs = np.random.RandomState(7)
    right = 0
    for k in range(500):
        d = k % 10
        _, pix = mlp_reference(layers, decoder_input(d, rs.randn(Z)))
        right += nn_reference(reader, np.array(pix, np.uint8))[0] == d
    print('project 16 reads %.1f %% of 500 new drawings as the digit that was asked for (shifts %s)'
          % (100 * right / 500, [l['shift'] for l in layers]))
    write_model(layers, 'trained on %d made-up digits; project 16 reads %.1f %% of its drawings right' % (len(X), 100 * right / 500))
    shutil.copy(os.path.join(HERE, '..', '16_digit_ai', 'nn_model.py'), os.path.join(HERE, 'reader_model.py'))
    print('wrote image_model.py (+ reader_model.py, the reader of project 16) in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
