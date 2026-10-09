"""19 AI Studio: train the big text model, write writer_big.py (PC, about an hour).

    python make_writer.py                     the Ardzy guides and Python's documentation strings
    python make_writer.py --text mybook.txt   your own text

Like project 17, but bigger: it reads the last 32 letters (17: 16), each letter becomes 16 learned numbers
-> 512 inputs -> 768 neurons -> 768 neurons -> one score per letter: about 1 000 000 weights (17: 127 000).
The AI Studio engine streams them from the board's DDR memory.
"""
import math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '17_text_ai'))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))
from nn_train import he, Adam, mlp_forward, mlp_backward, quantize_mlp, save_layers    # noqa: E402
from blocks import mlp_reference                                                        # noqa: E402
import make_model as tm17                                       # project 17's text collection and cleaning

CTX, EMB, H = 32, 16, 768


def train(ids, V, hold, epochs=3, per_epoch=1500000, seed=19, drop=.25):
    rs = np.random.RandomState(seed)
    sizes = [CTX * EMB, H, H, V]
    P = {'E': rs.randn(V, EMB).astype(np.float32) * .5}
    for i in range(3):
        P['W%d' % i] = he(rs, sizes[i], sizes[i + 1])
        P['b%d' % i] = np.zeros(sizes[i + 1], np.float32)
    opt = Adam(P, 1.5e-3)
    win = np.lib.stride_tricks.sliding_window_view(ids, CTX + 1)
    tr, va = win[:len(win) - hold], win[len(win) - hold:]
    for ep in range(epochs):
        lr = 1.5e-3 * .5 * (1 + math.cos(math.pi * ep / epochs))
        pick = rs.randint(0, len(tr), per_epoch)
        for s in range(0, per_epoch, 256):
            b = tr[pick[s:s + 256]]
            X, Y = b[:, :CTX], b[:, CTX]
            e = P['E'][X].reshape(len(b), -1)
            z, cache = mlp_forward(P, e, 3, rs, drop)
            z = z - z.max(1, keepdims=True); p = np.exp(z); p /= p.sum(1, keepdims=True)
            p[np.arange(len(b)), Y] -= 1
            G, de = mlp_backward(P, 3, p / len(b), cache)
            G['E'] = np.zeros_like(P['E'])
            np.add.at(G['E'], X, de.reshape(len(b), CTX, EMB))
            opt.step(G, lr)
        X, Y = va[:20000, :CTX], va[:20000, CTX]
        z, _ = mlp_forward(P, P['E'][X].reshape(len(X), -1), 3)
        z = z - z.max(1, keepdims=True)
        lp = z - np.log(np.exp(z).sum(1, keepdims=True))
        print('  round %d: %.2f bits per letter, next letter right %.1f %% (on text it never learned)'
              % (ep + 1, -lp[np.arange(len(X)), Y].mean() / math.log(2), 100 * (z.argmax(1) == Y).mean()), flush=True)
    return P, va


def main():
    t0 = time.time()
    if '--text' in sys.argv:
        src = sys.argv[sys.argv.index('--text') + 1]
        t = tm17.clean(open(src, encoding='utf-8', errors='replace').read())
        hold_text = t[int(len(t) * .97):]
        what = os.path.basename(src)
    else:
        a = tm17.ardzy_text()
        cut = int(len(a) * .93)
        t = tm17.clean('\n'.join([a[:cut]] * 3 + [tm17.python_text(4000000)] + [a[:cut]] * 3) + '\n')
        hold_text = tm17.clean(a[cut:])
        t = t + hold_text
        what = "the Ardzy guides and lessons and Python's documentation strings"
    vocab = tm17.make_vocab(t, 64)
    t = ''.join(c for c in t if c in vocab)
    hold = len([c for c in hold_text if c in vocab])
    ids = np.array([vocab.index(c) for c in t], np.int64)
    print('%d letters from %s, %d different: %r' % (len(t), what, len(vocab), vocab), flush=True)
    P, va = train(ids, len(vocab), hold)
    se = np.abs(P['E']).max() / 127
    Eq = np.clip(np.round(P['E'] / se), -127, 127).astype(np.int64)
    emb = (Eq + 128).astype(np.uint8)
    win = np.lib.stride_tricks.sliding_window_view(ids, CTX)[::11][:20000]
    Xb = emb[win].reshape(len(win), -1)
    Pq = {k: v for k, v in P.items() if k != 'E'}
    Pq['W0'] = P['W0']                                    # the embedding scale is part of the input bytes
    layers, scale = quantize_mlp(Pq, Xb, k_in=1 / se, offset=128)
    right = 0
    for w in va[-1500:]:
        right += mlp_reference(layers, emb[w[:CTX]].ravel())[0] == w[CTX]
    print('integers (the FPGA math): next letter right %.1f %% on text it never learned' % (100 * right / 1500))
    save_layers(os.path.join(HERE, 'writer_big.py'), layers,
                'the big text model (%d letters -> %d -> %d -> %d), learned from %s, next letter right %.1f %%'
                % (CTX, H, H, len(vocab), what, 100 * right / 1500),
                {'VOCAB': vocab, 'CTX': CTX, 'EMB': EMB, 'SCALE': scale, 'EMBED': emb})
    print('wrote writer_big.py in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
