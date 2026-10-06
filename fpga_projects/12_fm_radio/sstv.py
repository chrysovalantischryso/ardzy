"""sstv.py - pictures as sound (slow-scan television), for the Ardzy radio.

A picture is sent line by line as a tone whose pitch is the brightness: 1500 Hz = black, 2300 Hz = white,
1200 Hz pulses mark the start of a line. Before the picture, the VIS code (a few tones, 0.9 s) tells the
receiver which mode follows. Any receiver decodes it: a phone app (Robot36) listening to an FM radio, or
MMSSTV / QSSTV / SDR++ with an SDR in FM, AM or USB.

    Martin 1   320 x 256, colours G, B, R per line          114 s   (VIS 44)
    Scottie 1  320 x 256, G, B, then sync, then R           110 s   (VIS 60)
    Robot 36   320 x 240, brightness + colour difference    36 s    (VIS 8)

The picture comes as raw RGB bytes, 320 x 256 x 3 (the Ardzy app makes them from any image file).
"""
import array
import math

W, H = 320, 256
MODES = {
    'martin1': {'name': 'Martin 1', 'vis': 44, 'seconds': 114.3},
    'scottie1': {'name': 'Scottie 1', 'vis': 60, 'seconds': 109.6},
    'robot36': {'name': 'Robot 36', 'vis': 8, 'seconds': 36.0},
}


def freq(v):
    return 1500.0 + 800.0 * max(0, min(255, v)) / 255.0


def vis(code):
    segs = [(1900, 0.300), (1200, 0.010), (1900, 0.300), (1200, 0.030)]
    ones = 0
    for i in range(7):
        b = (code >> i) & 1
        ones += b
        segs.append((1100 if b else 1300, 0.030))
    segs.append((1100 if ones % 2 else 1300, 0.030))          # even parity
    segs.append((1200, 0.030))
    return segs


def _scan(row, seconds):
    px = seconds / len(row)
    return [(freq(v), px) for v in row]


def segments(rgb, mode):
    """(frequency, seconds) for the whole transmission. rgb: bytes, W x H x 3."""
    def chan(y, c):
        o = y * W * 3
        return rgb[o + c:o + W * 3:3]
    segs = vis(MODES[mode]['vis'])
    if mode == 'martin1':
        for y in range(H):
            segs += [(1200, 0.004862), (1500, 0.000572)]
            for c in (1, 2, 0):                                # G, B, R
                segs += _scan(chan(y, c), 0.146432) + [(1500, 0.000572)]
    elif mode == 'scottie1':
        segs.append((1200, 0.009))                            # the first line's sync
        for y in range(H):
            segs += [(1500, 0.0015)] + _scan(chan(y, 1), 0.13824) + [(1500, 0.0015)] + _scan(chan(y, 2), 0.13824)
            segs += [(1200, 0.009), (1500, 0.0015)] + _scan(chan(y, 0), 0.13824)
    elif mode == 'robot36':
        for y in range(240):
            src = y * H // 240
            o = src * W * 3
            ys, cs = [], []
            for x in range(W):
                r, g, b = rgb[o + 3 * x], rgb[o + 3 * x + 1], rgb[o + 3 * x + 2]
                ys.append(16 + (65.738 * r + 129.057 * g + 25.064 * b) / 256)
                if y % 2 == 0:
                    cs.append(128 + (112.439 * r - 94.154 * g - 18.285 * b) / 256)    # R-Y
                else:
                    cs.append(128 + (-37.945 * r - 74.494 * g + 112.439 * b) / 256)   # B-Y
            segs += [(1200, 0.009), (1500, 0.003)] + _scan(ys, 0.088)
            segs += [(1500 if y % 2 == 0 else 2300, 0.0045), (1900, 0.0015)]
            segs += _scan([sum(cs[2 * i:2 * i + 2]) / 2 for i in range(W // 2)], 0.044)
    else:
        raise ValueError('unknown SSTV mode ' + mode)
    return segs


def audio_words(rgb, mode, fs=22050, level=0.6, chunk=2048):
    """Yield lists of FIFO words (the same tone on left and right) at fs samples per second. The phase runs
    on without jumps, and the time is kept in whole samples of the whole transmission (no drift).
    With numpy the whole picture is made at once (about a second on the board's ARM); without it, sample by
    sample (too slow for live sending on the board, fine on a PC)."""
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        segs = segments(rgb, mode)
        carry, t_done, n_done = 0.0, 0.0, 0
        for k in range(0, len(segs), 4000):              # in blocks (about 2 s): little memory on the board
            part = segs[k:k + 4000]
            f = np.array([x[0] for x in part], dtype=np.float64)
            ends = np.round((t_done + np.cumsum(np.array([x[1] for x in part], dtype=np.float64))) * fs).astype(np.int64)
            t_done += sum(x[1] for x in part)
            counts = np.diff(np.concatenate(([n_done], ends))).astype(np.intp)   # (the board's numpy is 32-bit)
            n_done = int(ends[-1])
            phase = carry + np.cumsum(np.repeat(f, counts) / fs)
            if len(phase):
                carry = float(phase[-1] % 1.0)
            x = np.round(32767 * level * np.sin(2 * np.pi * phase)).astype(np.int16)
            w = x.view(np.uint16).astype(np.uint32) * 0x10001
            for i in range(0, len(w), chunk):
                yield w[i:i + chunk].tolist()
        yield [0] * int(0.2 * fs)
        return
    tab = array.array('i', [int(round(32767 * level * math.sin(2 * math.pi * i / 1024))) & 0xFFFF for i in range(1024)])
    tab = [v * 0x10001 for v in tab]
    ph, t, n_done, out = 0, 0.0, 0, []
    for f, sec in segments(rgb, mode):
        t += sec
        n = int(round(t * fs)) - n_done
        n_done += n
        inc = int(f / fs * 4294967296) & 0xFFFFFFFF
        for _ in range(n):
            ph = (ph + inc) & 0xFFFFFFFF
            out.append(tab[ph >> 22])
        if len(out) >= chunk:
            yield out
            out = []
    out += [0] * int(0.2 * fs)                                # a little silence at the end
    yield out


def test_picture():
    """Colour bars and a grey ramp: 320 x 256 RGB."""
    bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
    b = bytearray()
    for y in range(H):
        for x in range(W):
            if y < 160:
                b += bytes(bars[x * 8 // W])
            else:
                v = x * 255 // (W - 1)
                b += bytes((v, v, v))
    return bytes(b)
