"""19 AI Studio: train the big digit reader, write reader_big.py (PC, about 15 minutes).

    python make_reader.py

784 pixels -> 512 neurons -> 256 neurons -> 10 digits: 535 000 weights (project 16's reader has 51 000).
Too big for the FPGA's block RAM; the AI Studio engine streams it from the board's DDR memory.
The training digits come from project 16's digit maker (Windows fonts and pen strokes), 100 000 of them.
"""
import os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '16_digit_ai'))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))
from nn_train import train_mlp, quantize_mlp, save_layers     # noqa: E402
from blocks import mlp_reference                              # noqa: E402

SIZES = [784, 512, 256, 10]


def main():
    t0 = time.time()
    import make_model as dm                                  # project 16's digit maker
    fonts = dm.usable_fonts()
    import random
    random.Random(19).shuffle(fonts)
    X, Y = dm.make_set(fonts[12:], 50000, 50000, 19)
    Xv, Yv = dm.make_set(fonts[:12], 3000, 3000, 20)
    print('made %d training digits in %.0f s' % (len(X), time.time() - t0), flush=True)
    noisy = lambda b, rs: (b.astype(np.float32) / 255) * (rs.uniform(.8, 1, (len(b), 1)).astype(np.float32) if rs is not None else 1)
    P = train_mlp(X, Y, SIZES, epochs=18, drop=.2, seed=19, Xv=Xv, Yv=Yv, prepare=noisy)
    layers, scale = quantize_mlp(P, X, k_in=255)
    right = sum(mlp_reference(layers, x)[0] == y for x, y in zip(Xv[:2000], Yv[:2000]))
    print('integers (the FPGA math): %.2f %% right' % (100 * right / 2000))
    pick = np.concatenate([np.where(Yv == d)[0][:5] for d in range(10)])
    save_layers(os.path.join(HERE, 'reader_big.py'), layers,
                'the big digit reader %s, %.2f %% right on digits from fonts it never saw' % (SIZES, 100 * right / 2000),
                {'SCALE': scale, 'ACCURACY': right / 2000, 'TEST': Xv[pick].astype(np.uint8), 'TEST_LABELS': [int(v) for v in Yv[pick]]})
    print('wrote reader_big.py in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()
