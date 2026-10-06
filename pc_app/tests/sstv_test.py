"""Checks fpga_projects/12_fm_radio/sstv.py from the sound itself: the VIS code read from the tones, the
length of a whole picture, and the pixels measured from the pitch (colour bars and a grey ramp).

    python sstv_test.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'fpga_projects', '12_fm_radio'))
import sstv  # noqa: E402

FS = 22050
results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-46s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def samples(words):
    out = []
    for chunk in words:
        for w in chunk:
            v = w & 0xFFFF
            out.append(v - 65536 if v & 0x8000 else v)
    return out


def pitch(x, a, b):
    """The frequency of a pure tone in x[a:b] (from x[n-1] + x[n+1] = 2 cos(w) x[n])."""
    num = den = 0.0
    for n in range(max(1, a), min(len(x) - 1, b)):
        num += x[n] * (x[n - 1] + x[n + 1])
        den += 2 * x[n] * x[n]
    c = max(-1.0, min(1.0, num / den)) if den else 1.0
    return math.acos(c) * FS / (2 * math.pi)


def value(f):
    return (f - 1500) * 255 / 800


pic = sstv.test_picture()
for mode in ('martin1', 'scottie1', 'robot36'):
    x = samples(sstv.audio_words(pic, mode, FS))
    secs = len(x) / FS - 0.2
    want_secs = sstv.MODES[mode]['seconds'] + 0.91
    check('%s: length %.1f s' % (sstv.MODES[mode]['name'], secs), abs(secs - want_secs) < 0.6)
    # VIS: after 300 + 10 + 300 ms of leader and the 30 ms start bit, 8 bits of 30 ms
    bits = []
    for i in range(8):
        t0 = 0.640 + 0.030 * i
        f = pitch(x, int((t0 + 0.005) * FS), int((t0 + 0.025) * FS))
        bits.append(1 if f < 1200 else 0)
    code = sum(b << i for i, b in enumerate(bits[:7]))
    check('%s: VIS code %d, parity' % (sstv.MODES[mode]['name'], sstv.MODES[mode]['vis']),
          code == sstv.MODES[mode]['vis'] and sum(bits) % 2 == 0, 'read %d %s' % (code, bits))
    # pixels: walk the segment list (where each pixel is), measure the pitch in its middle part
    t, errs = 0.0, []
    segs = sstv.segments(pic, mode)
    expect = []
    for f, sec in segs:
        if sec < 0.0006 and 1500 <= f <= 2300 and sec > 0.0002:
            expect.append((t, sec, f))
        t += sec
    for t0, sec, f in expect[::7]:
        a, b = int((t0 + 0.2 * sec) * FS), int((t0 + 0.8 * sec) * FS)
        if b - a >= 4:
            errs.append(abs(value(pitch(x, a, b)) - value(f)))
    errs.sort()
    med, p90 = errs[len(errs) // 2], errs[int(len(errs) * 0.9)]
    check('%s: pixels from the pitch' % sstv.MODES[mode]['name'], med < 3 and p90 < 12,
          '%d pixels: error median %.1f, 90 %% below %.1f (of 255)' % (len(errs), med, p90))
print('RESULT: %d of %d ok' % (sum(results), len(results)))
