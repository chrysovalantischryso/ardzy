"""17 Text AI: train a small language model that writes text one letter at a time, write text_model.py (PC).

    python make_model.py                      learn from the Ardzy guides and lessons (English, about 300 KB)
    python make_model.py --text mybook.txt    learn from your own text instead (plain text, the more the better)

The model reads the last 16 letters and guesses the next one (it gives a score to every letter it knows).
Writing = guess, pick a letter (the likely ones more often), add it, guess again.

    16 letters -> each becomes 12 numbers (an "embedding", learned) -> 192 inputs
    -> 256 neurons (ReLU) -> 256 neurons (ReLU) -> one score per letter (about 48)

The three layers (126 000 weights) run in the FPGA's general network engine (mlp_engine.v); the embedding
is a small table the ARM looks up. Trained with floats, then turned into the engine's integers and checked
again with exactly the engine's math (mlp_reference in blocks.py).
"""
import base64, glob, html, math, os, re, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))
from blocks import mlp_reference                     # noqa: E402

CTX, EMB, H1, H2 = 16, 12, 256, 256
SEED = 17


def ardzy_text():
    """The English text of the Ardzy guides, lessons and documents, without code, tables and drawings."""
    root = os.path.normpath(os.path.join(HERE, '..', '..'))
    parts = []
    for f in sorted(glob.glob(os.path.join(root, 'fpga_projects', '*', 'guide.md'))) + [os.path.join(root, 'README.md')]:
        s = open(f, encoding='utf-8').read()
        s = re.sub(r'```[\s\S]*?```', ' ', s)
        s = re.sub(r'<(figure|svg|details)[\s\S]*?</\1>', ' ', s)
        s = '\n'.join(l for l in s.splitlines() if not l.lstrip().startswith(('|', '#', '<', '    ')))
        parts.append(s)
    for f in sorted(glob.glob(os.path.join(root, 'docs', '*.html'))):
        if '06_FPGA' in f:                         # = the guides above
            continue
        s = open(f, encoding='utf-8').read()
        s = re.sub(r'<(script|style|svg|pre|code|table)[\s\S]*?</\1>', ' ', s)
        parts.append(html.unescape(re.sub(r'<[^>]+>', ' ', s)))
    s = open(os.path.join(root, 'pc_app', 'ui', 'learn_data.js'), encoding='utf-8').read()
    parts += [m.replace("\\'", "'") for m in re.findall(r"'((?:[^'\\]|\\.){40,})'", s)]
    return '\n'.join(parts)


def python_text(limit=1500000):
    """More English: the documentation strings of Python's own standard library (PSF license), already on
    every PC with Python."""
    import ast
    lib = os.path.dirname(os.__file__)
    out, n = [], 0
    for root, dirs, files in os.walk(lib):
        dirs[:] = sorted(d for d in dirs if d not in ('test', 'tests', 'idlelib', 'site-packages', '__pycache__', 'lib2to3', 'turtledemo'))
        for f in sorted(files):
            if not f.endswith('.py'):
                continue
            try:
                tree = ast.parse(open(os.path.join(root, f), encoding='utf-8').read())
            except (SyntaxError, UnicodeDecodeError, ValueError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    d = ast.get_docstring(node)
                    if d and len(d) > 80 and '>>>' not in d:
                        out.append(d); n += len(d)
            if n > limit:
                return '\n'.join(out)
    return '\n'.join(out)


def clean(text):
    t = text.lower().replace('’', "'").replace('“', '"').replace('”', '"')
    t = re.sub(r'<[^>]{0,80}>', ' ', t)
    t = re.sub(r'\*\*|`|_', '', t)
    t = re.sub(r'[ \t\r\f\v]+', ' ', t)
    t = re.sub(r'\s*\n\s*', '\n', t)
    t = re.sub(r'\n{2,}', '\n', t)
    return t


def make_vocab(t, most=48):
    counts = {}
    for c in t:
        counts[c] = counts.get(c, 0) + 1
    chars = sorted(sorted(counts, key=lambda c: -counts[c])[:most])
    return ''.join(chars)


def train(ids, V, epochs, seed=SEED, hold=None):
    rs = np.random.RandomState(seed)
    P = {'E': rs.randn(V, EMB).astype(np.float32) * .5,
         'W1': (rs.randn(CTX * EMB, H1) * math.sqrt(2 / (CTX * EMB))).astype(np.float32), 'b1': np.zeros(H1, np.float32),
         'W2': (rs.randn(H1, H2) * math.sqrt(2 / H1)).astype(np.float32), 'b2': np.zeros(H2, np.float32),
         'W3': (rs.randn(H2, V) * math.sqrt(2 / H2)).astype(np.float32), 'b3': np.zeros(V, np.float32)}
    M = {k: np.zeros_like(v) for k, v in P.items()}
    S = {k: np.zeros_like(v) for k, v in P.items()}
    n = len(ids) - CTX
    split = n - hold if hold else int(n * .95)    # the end of the text is only for checking, never learned
    win = np.lib.stride_tricks.sliding_window_view(ids, CTX + 1)
    tr, va = win[:split], win[split:]
    step = 0
    for ep in range(epochs):
        lr = 2e-3 * .5 * (1 + math.cos(math.pi * ep / epochs))
        order = rs.permutation(len(tr))
        for s in range(0, len(tr), 256):
            b = tr[order[s:s + 256]]
            X, Y = b[:, :CTX], b[:, CTX]
            e = P['E'][X].reshape(len(b), -1)
            a1 = e @ P['W1'] + P['b1']; h1 = np.maximum(a1, 0)
            a2 = h1 @ P['W2'] + P['b2']; h2 = np.maximum(a2, 0)
            z = h2 @ P['W3'] + P['b3']
            z -= z.max(1, keepdims=True); p = np.exp(z); p /= p.sum(1, keepdims=True)
            p[np.arange(len(b)), Y] -= 1; p /= len(b)
            G = {'W3': h2.T @ p, 'b3': p.sum(0)}
            d2 = (p @ P['W3'].T) * (a2 > 0)
            G['W2'] = h1.T @ d2; G['b2'] = d2.sum(0)
            d1 = (d2 @ P['W2'].T) * (a1 > 0)
            G['W1'] = e.T @ d1; G['b1'] = d1.sum(0)
            de = (d1 @ P['W1'].T).reshape(len(b), CTX, EMB)
            G['E'] = np.zeros_like(P['E']); np.add.at(G['E'], X, de)
            step += 1
            for k in P:
                g = G[k] + (1e-5 * P[k] if k[0] == 'W' else 0)
                M[k] = .9 * M[k] + .1 * g; S[k] = .999 * S[k] + .001 * g * g
                P[k] -= lr * (M[k] / (1 - .9 ** step)) / (np.sqrt(S[k] / (1 - .999 ** step)) + 1e-8)
        loss, acc = evaluate(P, va[:20000])
        print('  round %2d: %.2f bits per letter, next letter right %.1f %%' % (ep + 1, loss / math.log(2), 100 * acc), flush=True)
    return P, va


def evaluate(P, va):
    X, Y = va[:, :CTX], va[:, CTX]
    e = P['E'][X].reshape(len(va), -1)
    z = np.maximum(np.maximum(e @ P['W1'] + P['b1'], 0) @ P['W2'] + P['b2'], 0) @ P['W3'] + P['b3']
    z -= z.max(1, keepdims=True)
    lp = z - np.log(np.exp(z).sum(1, keepdims=True))
    return -lp[np.arange(len(va)), Y].mean(), (z.argmax(1) == Y).mean()


def quantize(P, ids):
    """The engine's integers. The embedding becomes bytes 0..255 (value + 128); the +128 is taken back out
    through layer 1's biases, so the result is the same as with signed numbers."""
    se = np.abs(P['E']).max() / 127
    Eq = np.clip(np.round(P['E'] / se), -127, 127).astype(np.int64)
    s1 = np.abs(P['W1']).max() / 127
    W1 = np.clip(np.round(P['W1'] / s1), -127, 127).astype(np.int64)            # (192, H1)
    b1 = np.round(P['b1'] / (s1 * se)).astype(np.int64) - 128 * W1.sum(0)
    win = np.lib.stride_tricks.sliding_window_view(ids, CTX)[::7][:30000]
    X = (Eq[win] + 128).reshape(len(win), -1)
    acc1 = X @ W1 + b1
    sh1 = max(0, int(math.ceil(math.log2(np.percentile(acc1[acc1 > 0], 99.9) / 255))))
    h1 = np.clip(acc1 >> sh1, 0, 255)
    k1 = 1 / (s1 * se * 2 ** sh1)                                  # h1 integer = h1 float * k1
    s2 = np.abs(P['W2']).max() / 127
    W2 = np.clip(np.round(P['W2'] / s2), -127, 127).astype(np.int64)
    b2 = np.round(P['b2'] * k1 / s2).astype(np.int64)
    acc2 = h1 @ W2 + b2
    sh2 = max(0, int(math.ceil(math.log2(np.percentile(acc2[acc2 > 0], 99.9) / 255))))
    k2 = k1 / s2 / 2 ** sh2
    s3 = np.abs(P['W3']).max() / 127
    W3 = np.clip(np.round(P['W3'] / s3), -127, 127).astype(np.int64)
    b3 = np.round(P['b3'] * k2 / s3).astype(np.int64)
    layers = [{'w': W1.T.astype(np.int8), 'b': b1, 'shift': sh1, 'act': 1},
              {'w': W2.T.astype(np.int8), 'b': b2, 'shift': sh2, 'act': 1},
              {'w': W3.T.astype(np.int8), 'b': b3, 'shift': 0, 'act': 0}]
    return layers, (Eq + 128).astype(np.uint8), float(s3 / k2)       # score * scale = the float score


def int_check(layers, emb, ids, n=1500):
    win = np.lib.stride_tricks.sliding_window_view(ids, CTX + 1)[-n:]
    right = 0
    for w in win:
        d, _ = mlp_reference(layers, emb[w[:CTX]].ravel())
        right += d == w[CTX]
    return right / len(win)


def write_model(layers, emb, vocab, scale, info):
    b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
    L = ['# Generated by make_model.py: the trained text model (do not edit; run make_model.py again).', '# ' + info,
         'VOCAB = %r' % vocab, 'CTX = %d' % CTX, 'EMB = %d' % EMB, 'SCALE = %.6g' % scale,
         'SHIFTS = %r' % [l['shift'] for l in layers], 'ACTS = %r' % [l['act'] for l in layers],
         'SHAPES = %r' % [list(l['w'].shape) for l in layers]]
    for k, l in enumerate(layers):
        L.append('B%d = %r' % (k + 1, [int(v) for v in l['b']]))
    for name, a in [('EMBED', emb)] + [('W%d' % (k + 1), l['w']) for k, l in enumerate(layers)]:
        s = b64(a)
        L.append('%s = (' % name)
        L += ["    '%s'" % s[i:i + 100] for i in range(0, len(s), 100)]
        L.append(')')
    open(os.path.join(HERE, 'text_model.py'), 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')


def sample(layers, emb, vocab, start, n=300, temp=0.7, seed=1):
    rng = np.random.RandomState(seed)
    ids = [vocab.index(c) for c in start if c in vocab]
    ids = [vocab.index(' ')] * CTX + ids
    out = ''
    for _ in range(n):
        _, s = mlp_reference(layers, emb[ids[-CTX:]].ravel())
        z = np.array(s, float) * SCALE_ / temp
        p = np.exp(z - z.max()); p /= p.sum()
        c = rng.choice(len(vocab), p=p)
        ids.append(c); out += vocab[c]
    return out


def main():
    global SCALE_
    t0 = time.time()
    if '--text' in sys.argv:
        src = sys.argv[sys.argv.index('--text') + 1]
        text, what = open(src, encoding='utf-8', errors='replace').read(), os.path.basename(src)
    else:
        a = ardzy_text()
        cut = int(len(a) * .93)                 # the end of the Ardzy text is never learned: it is for checking
        text, what = ('\n'.join([a[:cut]] * 3 + [python_text(700000)] + [a[:cut]] * 3) + '\n' + a[cut:],
                      "the Ardzy guides and lessons (6 times) and Python's documentation strings")
    t = clean(text)
    vocab = make_vocab(t)
    t = ''.join(c for c in t if c in vocab)
    ids = np.array([vocab.index(c) for c in t], np.int64)
    print('%d letters of text from %s, %d different letters: %r' % (len(t), what, len(vocab), vocab), flush=True)
    epochs = int(sys.argv[sys.argv.index('--rounds') + 1]) if '--rounds' in sys.argv else 10
    hold = len(clean(a[cut:])) if '--text' not in sys.argv else len(ids) // 20
    P, va = train(ids, len(vocab), epochs, hold=hold)
    layers, emb, SCALE_ = quantize(P, ids)
    acc = int_check(layers, emb, ids)
    print('integers (the FPGA math): next letter right %.1f %% (shifts %s)' % (100 * acc, [l['shift'] for l in layers]))
    print('example:', repr(sample(layers, emb, vocab, 'the fpga ', 200)))
    write_model(layers, emb, vocab, SCALE_, 'learned from %s: %d letters, next letter right %.1f %% (FPGA integers)' % (what, len(t), 100 * acc))
    print('wrote text_model.py in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
