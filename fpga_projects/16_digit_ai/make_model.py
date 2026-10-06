"""16 AI in the FPGA: make the training digits, train the neural network, write nn_model.py (runs on the PC).

    python make_model.py            (about 2 minutes; needs numpy and Pillow, and Windows for the fonts)

No downloaded data set: the digits are made here, in two ways, so that they look like digits drawn
with a mouse or a finger:
  * written in about 90 fonts of Windows (normal, bold, italic, handwriting fonts), and
  * drawn as pen strokes from a sketch of each digit (several ways to write 1, 4, 7, 9 ...).
Each one is turned a bit, slanted, made bigger or smaller, thinner or bolder, then prepared the same
way the drawing page prepares your drawing (digit_preprocess in blocks.py: cut out, 20 x 20, centred
in 28 x 28).

The network: 784 inputs (the 28 x 28 pixels) -> HID hidden neurons (ReLU) -> 10 outputs, one per digit.
It is trained with floats, then turned into the integers the FPGA uses (8-bit weights, 32-bit sums) and
checked again with exactly the FPGA's integer math (nn_reference in blocks.py).
"""
import base64, glob, math, os, random, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))
from blocks import digit_preprocess, nn_reference     # noqa: E402  (the same code runs on the board)

HID = 64                # hidden neurons: 16 lanes x 4 rows in the FPGA
CANVAS = 112            # the drawing page sends 112 x 112 pixels
SEED = 16
SKIP_FONTS = ('marlett', 'symbol', 'webdings', 'wingding', 'wingdng', 'segmdl2', 'segoeicons', 'seguiemj',
              'himalaya', 'javatext', 'l_10646', 'ttsnote', 'msyi', 'phagspa', 'mmrtext', 'monbaiti', 'taile', 'ntailu')

# ------------------------------------------------------------------ digits as pen strokes
def arc(cx, cy, rx, ry, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


SKETCH = {      # each digit: a few ways to write it; each way: strokes; each stroke: points (0..1, y down)
    0: [[arc(.5, .5, .32, .45, -90, 270)], [arc(.5, .5, .26, .45, -100, 255)], [arc(.5, .5, .36, .44, -80, 285)]],
    1: [[[(.55, .05), (.55, .95)]], [[(.32, .25), (.58, .05), (.58, .95)]],
        [[(.35, .22), (.56, .05), (.56, .95)], [(.32, .95), (.8, .95)]], [[(.62, .05), (.45, .95)]]],
    2: [[arc(.5, .3, .3, .25, 180, 360) + [(.15, .95), (.85, .95)]],
        [arc(.5, .32, .32, .27, 200, 380) + [(.2, .95), (.88, .92)]],
        [arc(.5, .3, .3, .25, 170, 330) + [(.12, .95), (.5, .85), (.9, .95)]]],
    3: [[arc(.5, .28, .3, .23, 200, 450), arc(.5, .72, .33, .25, -90, 160)],
        [arc(.5, .28, .3, .23, 200, 450) + arc(.5, .72, .33, .25, -90, 160)],
        [[(.18, .05), (.82, .05), (.45, .42)] + arc(.5, .7, .33, .27, -100, 160)]],
    4: [[[(.65, .95), (.65, .05), (.12, .68), (.88, .68)]],
        [[(.22, .05), (.15, .6), (.85, .6)], [(.65, .3), (.65, .95)]],
        [[(.25, .05), (.2, .55), (.8, .55)], [(.7, .05), (.7, .95)]]],
    5: [[[(.82, .05), (.25, .05), (.2, .45)] + arc(.5, .68, .32, .27, 200, 510)],
        [[(.25, .05), (.2, .45)] + arc(.5, .68, .32, .27, 200, 510), [(.25, .05), (.82, .05)]]],
    6: [[[(.75, .05), (.45, .22), (.25, .55)] + arc(.5, .7, .27, .25, 180, 540)],
        [[(.7, .05), (.3, .4)] + arc(.5, .7, .3, .25, 200, 560)]],
    7: [[[(.12, .05), (.88, .05), (.4, .95)]], [[(.12, .05), (.88, .05), (.45, .95)], [(.35, .5), (.78, .5)]],
        [[(.15, .15), (.15, .05), (.85, .05), (.55, .95)]]],
    8: [[arc(.5, .27, .24, .22, 90, 450), arc(.5, .72, .3, .25, -90, 270)],
        [arc(.5, .27, .25, .22, 135, 495) + arc(.5, .72, .3, .25, -45, 315)]],
    9: [[arc(.5, .3, .27, .25, 0, 360) + [(.77, .3), (.7, .95)]],
        [arc(.5, .3, .27, .25, 0, 360) + [(.77, .3)] + arc(.45, .7, .32, .28, 0, 110)],
        [arc(.5, .3, .27, .25, 10, 370) + [(.77, .3), (.77, .95)]]],
}


def stroke_digit(d, rng):
    way = rng.choice(SKETCH[d])
    img = Image.new('L', (CANVAS * 2, CANVAS * 2), 0)
    g = ImageDraw.Draw(img)
    width = rng.uniform(5, 15) * 2
    j = rng.uniform(0, .035)
    for stroke in way:
        pts = [((x + rng.gauss(0, j)) * CANVAS * 1.4 + CANVAS * .3, (y + rng.gauss(0, j)) * CANVAS * 1.4 + CANVAS * .3)
               for x, y in stroke]
        g.line(pts, fill=255, width=int(width), joint='curve')
        r = width / 2
        for x, y in (pts[0], pts[-1]):
            g.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return img


# ------------------------------------------------------------------ digits from fonts
def usable_fonts():
    out = []
    for f in sorted(glob.glob(r'C:\Windows\Fonts\*.tt[fc]') + glob.glob(r'C:\Windows\Fonts\*.TTF')):
        if any(s in os.path.basename(f).lower() for s in SKIP_FONTS):
            continue
        try:
            font = ImageFont.truetype(f, 150)
            shapes = []
            for d in range(10):
                im = Image.new('L', (200, 200), 0)
                ImageDraw.Draw(im).text((100, 100), str(d), font=font, fill=255, anchor='mm')
                a = np.asarray(im, dtype=np.float32) / 255
                if a.sum() < 50:
                    raise ValueError('no glyph')
                shapes.append(digit_preprocess(a).astype(np.float32).ravel())
            m = np.array(shapes)
            dist = np.abs(m[:, None, :] - m[None, :, :]).mean(axis=2) + np.eye(10) * 1e9
            if dist.min() < 6:            # two digits look the same: a missing glyph or a symbol font
                raise ValueError('digits look alike')
            out.append(f)
        except Exception:
            pass
    return out


def font_digit(font_file, d, rng):
    font = ImageFont.truetype(font_file, int(rng.uniform(120, 170)))
    img = Image.new('L', (CANVAS * 2, CANVAS * 2), 0)
    ImageDraw.Draw(img).text((CANVAS, CANVAS), str(d), font=font, fill=255, anchor='mm',
                             stroke_width=int(rng.choice([0, 0, 0, 2, 4, 7])), stroke_fill=255)
    return img


# ------------------------------------------------------------------ the same changes for both
def augment(img, rng):
    a = math.radians(rng.uniform(-14, 14))
    sh = rng.uniform(-.3, .3)
    sx, sy = rng.uniform(.75, 1.15), rng.uniform(.85, 1.15)
    c = CANVAS
    m = np.array([[math.cos(a) / sx, (math.sin(a) + sh) / sx], [-math.sin(a) / sy, math.cos(a) / sy]])
    off = np.array([c, c]) - m @ np.array([c, c])
    img = img.transform(img.size, Image.AFFINE, (m[0, 0], m[0, 1], off[0], m[1, 0], m[1, 1], off[1]), Image.BILINEAR)
    img = img.resize((CANVAS, CANVAS), Image.BOX)
    x = np.asarray(img, dtype=np.float32) / 255
    if rng.random() < .3:                  # thicker or thinner, like another pen
        k = rng.choice([-1, 1])
        p = np.pad(x, 1)
        n = [p[1 + dy:1 + dy + CANVAS, 1 + dx:1 + dx + CANVAS] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        x = np.max(n, axis=0) if k > 0 else np.min(n, axis=0)
    return digit_preprocess(x)


def make_set(fonts, n_font, n_stroke, seed):
    rng = random.Random(seed)
    X, Y = [], []
    for i in range(n_font):
        d = i % 10
        X.append(augment(font_digit(rng.choice(fonts), d, rng), rng)); Y.append(d)
    for i in range(n_stroke):
        d = i % 10
        X.append(augment(stroke_digit(d, rng), rng)); Y.append(d)
    return np.array(X, dtype=np.uint8).reshape(len(X), 784), np.array(Y)


# ------------------------------------------------------------------ the network
def train(X, Y, Xv, Yv, epochs=24, seed=SEED):
    rs = np.random.RandomState(seed)
    W1 = rs.randn(784, HID).astype(np.float32) * math.sqrt(2 / 784)
    b1 = np.zeros(HID, np.float32)
    W2 = rs.randn(HID, 10).astype(np.float32) * math.sqrt(2 / HID)
    b2 = np.zeros(10, np.float32)
    P = [W1, b1, W2, b2]
    M = [np.zeros_like(p) for p in P]
    V = [np.zeros_like(p) for p in P]
    Xf = X.astype(np.float32) / 255
    t = 0
    for ep in range(epochs):
        lr = 2e-3 * (0.5 * (1 + math.cos(math.pi * ep / epochs)))
        idx = rs.permutation(len(X))
        for s in range(0, len(X), 128):
            b = idx[s:s + 128]
            x = Xf[b] * rs.uniform(.8, 1.0, (len(b), 1)).astype(np.float32)
            h = np.maximum(x @ W1 + b1, 0)
            hd = h * (rs.rand(*h.shape) > .15) / .85             # dropout
            z = hd @ W2 + b2
            z -= z.max(1, keepdims=True)
            p = np.exp(z); p /= p.sum(1, keepdims=True)
            p[np.arange(len(b)), Y[b]] -= 1
            p /= len(b)
            gW2 = hd.T @ p + 1e-4 * W2; gb2 = p.sum(0)
            dh = (p @ W2.T) * (hd > 0) / .85
            gW1 = x.T @ dh + 1e-4 * W1; gb1 = dh.sum(0)
            t += 1
            for i, g in enumerate([gW1, gb1, gW2, gb2]):
                M[i] = .9 * M[i] + .1 * g
                V[i] = .999 * V[i] + .001 * g * g
                P[i] -= lr * (M[i] / (1 - .9 ** t)) / (np.sqrt(V[i] / (1 - .999 ** t)) + 1e-8)
        acc = (np.argmax(np.maximum(Xv.astype(np.float32) / 255 @ W1 + b1, 0) @ W2 + b2, 1) == Yv).mean()
        print('  epoch %2d: %.1f %% right on digits it never saw' % (ep + 1, 100 * acc), flush=True)
    return P


def quantize(P, X):
    """Floats -> the FPGA's integers. Pixels stay 0..255. Hidden values: 0..255 after >> SHIFT."""
    W1, b1, W2, b2 = P
    s1 = np.abs(W1).max() / 127
    W1q = np.clip(np.round(W1 / s1), -127, 127).astype(np.int8)
    b1q = np.round(b1 * 255 / s1).astype(np.int64)
    acc = X.astype(np.int64) @ W1q.astype(np.int64) + b1q
    top = np.percentile(acc[acc > 0], 99.9)
    shift = max(0, int(math.ceil(math.log2(top / 255))))
    hscale = 255 / s1 / 2 ** shift                       # hidden integer = float hidden * hscale
    s2 = np.abs(W2).max() / 127
    W2q = np.clip(np.round(W2 / s2), -127, 127).astype(np.int8)
    b2q = np.round(b2 * hscale / s2).astype(np.int64)
    return {'hid': HID, 'shift': shift, 'w1': W1q.T.copy(), 'b1': b1q, 'w2': W2q.T.copy(), 'b2': b2q,
            'scale': float(s2 / hscale)}           # score * scale = the float network's output (for percentages)


def write_model(q, Xt, Yt, acc_int, info):
    b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
    lines = ['# Generated by make_model.py: the trained network for the FPGA (do not edit; run make_model.py again).',
             '# %s' % info,
             'HID = %d' % q['hid'], 'SHIFT = %d' % q['shift'], 'ACCURACY = %.4f' % acc_int, 'SCALE = %.6g' % q['scale'],
             'B1 = %r' % [int(v) for v in q['b1']], 'B2 = %r' % [int(v) for v in q['b2']],
             'TEST_LABELS = %r' % [int(v) for v in Yt]]
    for name, a in (('W1', q['w1']), ('W2', q['w2']), ('TEST', Xt)):
        s = b64(a)
        lines.append('%s = (' % name)
        lines += ["    '%s'" % s[i:i + 100] for i in range(0, len(s), 100)]
        lines.append(')')
    open(os.path.join(HERE, 'nn_model.py'), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')


def main():
    t0 = time.time()
    fonts = usable_fonts()
    print('%d fonts with clear digits' % len(fonts), flush=True)
    rng = random.Random(SEED)
    rng.shuffle(fonts)
    test_fonts, train_fonts = fonts[:12], fonts[12:]          # some fonts are only in the test
    X, Y = make_set(train_fonts, 30000, 30000, SEED)
    Xv, Yv = make_set(test_fonts, 3000, 3000, SEED + 1)
    print('made %d training and %d test digits in %.0f s' % (len(X), len(Xv), time.time() - t0), flush=True)
    P = train(X, Y, Xv, Yv)
    q = quantize(P, X)
    pred = np.array([nn_reference(q, x)[0] for x in Xv])
    acc_int = (pred == Yv).mean()
    print('integers (the FPGA math): %.1f %% right, shift %d' % (100 * acc_int, q['shift']))
    for d in range(10):
        print('  digit %d: %.1f %%' % (d, 100 * (pred[Yv == d] == d).mean()))
    pick = np.concatenate([np.where(Yv == d)[0][:5] for d in range(10)])   # 50 test digits for the board
    write_model(q, Xv[pick], Yv[pick], acc_int,
                '%d fonts + pen strokes, %d training digits, %.1f %% on unseen fonts and strokes' % (len(fonts), len(X), 100 * acc_int))
    print('wrote nn_model.py in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
