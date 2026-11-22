"""Checks of the radio's new signals on the PC (no board needed): every signal is made by the same code the
board runs (fpga_projects/12_fm_radio) and then measured or decoded back here.

    python radio_modes_test.py

  WSPR       the 162 symbols of 4 messages against another program's results (the Rust crate `wspr`)
  paint      the waterfall picture: made, then looked at with an FFT like an SDR does, line by line
  Hell       the dots of a letter come back from the symbols
  QRSS/PSK   timings
  APRS       the AX.25 frame: HDLC decoded back from the AFSK tones, CRC checked
  DTMF       each digit's two tones found again
  WEFAX      line timing, start and stop tones
  SSTV       the length of every mode
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'fpga_projects', '12_fm_radio')))
import audio_modes  # noqa: E402
import font  # noqa: E402
import modes  # noqa: E402
import paint  # noqa: E402
import sstv  # noqa: E402

results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('%-4s %-58s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def vec(s):
    return [int(x) for x in s.replace('\n', ' ').split(',')]


# ---------------------------------------------------------------- WSPR
WSPR_VECTORS = [
    ('K1A', 'FN34', 33, '''3, 3, 0, 0, 2, 2, 0, 0, 1, 2, 0, 0, 1, 1, 1, 0, 2, 0, 3, 0, 0,
  3, 0, 1, 1, 3, 3, 0, 0, 0, 0, 2, 0, 2, 1, 0, 0, 3, 2, 1, 2, 0,
  2, 0, 0, 0, 3, 0, 1, 3, 0, 2, 3, 1, 2, 3, 0, 2, 0, 3, 3, 0, 1,
  2, 2, 0, 0, 1, 3, 2, 1, 0, 3, 2, 3, 2, 1, 0, 0, 3, 2, 2, 1, 2,
  1, 1, 0, 0, 0, 1, 1, 0, 3, 2, 3, 2, 2, 2, 3, 0, 2, 2, 0, 0, 1,
  2, 2, 1, 2, 0, 1, 3, 1, 2, 3, 3, 0, 0, 1, 1, 2, 3, 2, 2, 0, 3,
  1, 3, 2, 2, 0, 2, 0, 3, 0, 3, 2, 0, 1, 1, 2, 2, 0, 0, 2, 2, 2,
  1, 3, 2, 3, 2, 3, 1, 2, 0, 0, 3, 1, 2, 2, 2'''),
    ('N6AB', 'CM87', 0, '''3, 1, 0, 0, 2, 2, 0, 2, 1, 0, 2, 0, 1, 3, 3, 0, 2, 0, 3, 0, 0,
  1, 2, 1, 3, 1, 1, 2, 0, 2, 0, 0, 0, 2, 3, 2, 0, 1, 0, 3, 2, 0,
  0, 0, 0, 2, 1, 0, 1, 3, 2, 0, 3, 1, 2, 1, 2, 0, 2, 3, 3, 0, 3,
  0, 2, 2, 2, 3, 3, 0, 3, 2, 3, 2, 3, 2, 3, 0, 2, 1, 2, 2, 1, 0,
  1, 3, 2, 2, 0, 1, 1, 0, 1, 2, 1, 0, 2, 2, 1, 0, 0, 2, 2, 0, 1,
  0, 2, 3, 0, 2, 1, 1, 1, 0, 3, 3, 2, 0, 3, 1, 0, 3, 2, 0, 0, 3,
  3, 1, 2, 2, 2, 2, 2, 3, 0, 1, 2, 0, 1, 1, 0, 2, 2, 0, 2, 2, 2,
  3, 3, 2, 1, 2, 1, 3, 0, 0, 0, 3, 1, 0, 2, 2'''),
    ('G1ABC', 'IO83', 37, '''3, 3, 0, 0, 0, 2, 0, 0, 1, 0, 2, 0, 1, 1, 3, 2, 2, 2, 3, 2, 2,
  1, 0, 1, 1, 3, 1, 2, 2, 2, 0, 0, 0, 0, 3, 0, 0, 1, 0, 3, 0, 2,
  2, 2, 0, 2, 3, 2, 1, 3, 2, 2, 3, 3, 0, 1, 0, 0, 0, 1, 3, 2, 3,
  2, 2, 2, 0, 1, 1, 2, 3, 0, 3, 0, 1, 0, 3, 0, 0, 1, 2, 2, 3, 2,
  3, 3, 0, 0, 2, 3, 1, 2, 1, 0, 1, 2, 2, 2, 1, 0, 2, 0, 2, 2, 3,
  2, 0, 1, 0, 0, 3, 1, 1, 2, 3, 3, 2, 2, 1, 1, 2, 1, 2, 0, 0, 1,
  3, 3, 2, 0, 0, 2, 2, 1, 2, 3, 2, 0, 1, 1, 2, 2, 2, 2, 2, 0, 2,
  3, 3, 2, 1, 2, 1, 3, 0, 2, 2, 3, 3, 2, 2, 0'''),
    ('KA1BCD', 'AA00', 33, '''3, 3, 2, 2, 0, 2, 0, 2, 3, 2, 0, 2, 1, 1, 1, 0, 0, 2, 1, 0, 2,
  3, 2, 1, 1, 1, 1, 0, 0, 2, 0, 2, 2, 0, 3, 2, 2, 3, 2, 3, 2, 2,
  2, 0, 2, 0, 3, 0, 3, 1, 0, 2, 3, 1, 0, 3, 2, 2, 0, 1, 3, 2, 1,
  2, 0, 2, 0, 3, 3, 0, 3, 2, 1, 2, 1, 0, 3, 0, 2, 3, 0, 0, 3, 0,
  3, 3, 2, 0, 2, 1, 1, 0, 3, 0, 3, 2, 2, 0, 3, 2, 0, 0, 2, 0, 3,
  2, 0, 1, 2, 2, 1, 3, 1, 2, 1, 3, 2, 0, 1, 1, 2, 3, 0, 0, 2, 1,
  3, 3, 2, 0, 2, 2, 2, 3, 0, 1, 2, 2, 1, 1, 0, 2, 0, 0, 0, 0, 2,
  3, 1, 2, 1, 2, 3, 3, 2, 2, 2, 3, 1, 2, 0, 2'''),
]
for call, loc, dbm, want in WSPR_VECTORS:
    got = modes.wspr_symbols(call, loc, dbm)
    w = vec(want)
    diff = sum(1 for a, b in zip(got, w) if a != b)
    check('WSPR %s %s %d: 162 symbols as another encoder makes them' % (call, loc, dbm), got == w and len(w) == 162,
          '%d of 162 differ' % diff)
check('WSPR: bad messages are refused', all(modes.wspr_check(*m) for m in
      [('K1ABCDE', 'FN42', 30), ('K1ABC', 'ZZ42', 30), ('K1ABC', 'FN42', 31), ('ABC', 'FN42', 30)]))
sy = modes.wspr('G1ABC', 'IO83', 37, offset_hz=1500)
check('WSPR: 110.6 s, tones within 1500 Hz +- 3 Hz', abs(modes.duration_s(sy) - 110.592) < 0.01 and
      all(abs(s[0] - 1500) < 3 for s in sy), '%.3f s' % modes.duration_s(sy))
check('WSPR: the next slot starts 1 s after an even minute',
      modes.wspr_next_start(1000000000.0) % 120 == 1 and modes.wspr_next_start(1000000000.0) >= 1000000000.0)

# ---------------------------------------------------------------- timing
q = modes.quantize([(0, 2.5e6, 512, 0), (0, 0.4, 0, 0), (0, 0.4, 0, 0), (0, 0.4, 0, 0)])
check('timing: long symbols cut at 1 s, fractions carried on', max(x[1] for x in q) <= 1000000 and
      sum(x[1] for x in q) == 2500001, str([x[1] for x in q]))
r = modes.quantize(modes.rtty('RYRY ' * 20))
check('timing: RTTY keeps time over a long message', abs(sum(x[1] for x in r) / 1e6 - modes.duration_s(modes.rtty('RYRY ' * 20))) < 1e-5)
for name, baud in modes.PSK_BAUDS.items():
    p = modes.psk31('test', baud=baud)
    bits = len(modes.psk31_bits('test')) + 2 * max(0, int(round(baud / 31.25)) - 1) * 32
    check('%s: %.2f baud, %d bits' % (name.upper(), baud, bits), abs(modes.duration_s(p) - bits / baud - 0.001) < 1e-3)
qs = modes.qrss('E', dot_s=3)
on = sum(s[1] for s in qs if s[2] > 0) / 1e6
check('QRSS3: a dot is 3 s of carrier', abs(on - 3.0) < 0.01, '%.2f s' % on)
df = modes.qrss('ET', dot_s=3, dfcw_hz=5)
check('DFCW: a dash is 5 Hz above a dot, same length', sorted({s[0] for s in df if s[2] > 0}) == [0.0, 5.0] and
      len({s[1] for s in df if s[2] > 0}) == 1)

# ---------------------------------------------------------------- Hell
h = modes.hell('H')
t, dots = 0.0, []
px = 1e6 / modes.HELL_BAUD
on_t = np.zeros(int(sum(s[1] for s in h) / px) + 2)
for off, us, w, ph in h:                       # how much ink each dot slot got
    a, b = t / px, (t + us) / px
    if w > 0:
        for k in range(int(a), int(math.ceil(b))):
            on_t[k] += min(b, k + 1) - max(a, k)
    t += us
got = (on_t > 0.5).astype(int)
cols = got[7 * 14:14 * 14].reshape(7, 14)[:, ::-1]           # the H (after the leading space), top row first
want = np.repeat(font.glyph('H'), 2, axis=0).T
want = np.vstack([want, np.zeros((2, 14), int)])
check('Hell: the letter H comes back from the dots', np.array_equal(cols, want))
check('Hell: 122.5 dots a second, 0.8 s a letter', abs(modes.duration_s(modes.hell('AB')) - 4 * 98 / 122.5) < 1e-3,
      '%.3f s for 4 letters with spaces' % modes.duration_s(modes.hell('AB')))

# ---------------------------------------------------------------- the waterfall picture
FS = paint.FS
for kind, width, off in (('iq', 20000.0, 0.0), ('iq', 8000.0, 6000.0), ('usb', 2400.0, 0.0)):
    img = paint.test_picture(48, 36)
    s = dict(paint.DEFAULT, kind=kind, width_hz=width, offset_hz=off, line_ms=100, edge_ms=3, contrast_db=30)
    pt = paint.Painter(img, s).start()
    w = np.concatenate(list(pt.words()))
    i = (w & 0xFFFF).astype(np.uint16).view(np.int16).astype(np.float64) / 32767
    qv = (w >> 16).astype(np.uint16).view(np.int16).astype(np.float64) / 32767
    z = i + 1j * qv if kind == 'iq' else i
    peak = np.max(np.abs(z))
    n_line = pt.line_n
    # look at each line like a waterfall: an FFT in the middle of the line, the level at each column's tone
    nf = 4096
    win = np.hanning(nf)
    seen = []
    for y in range(pt.lines):
        mid = y * n_line + n_line // 2
        seg = z[mid - nf // 2:mid + nf // 2]
        if len(seg) < nf:
            seg = np.concatenate([seg, np.zeros(nf - len(seg))])
        sp = np.abs(np.fft.fft(seg * win))
        f = pt.low + np.arange(pt.columns) * pt.step * paint.BIN
        k = np.round(f / FS * nf).astype(int) % nf
        seen.append(20 * np.log10(np.maximum(1e-9, np.maximum(sp[k], np.maximum(sp[(k + 1) % nf], sp[k - 1])))))
    seen = np.array(seen)[::-1]                # (sent bottom line first)
    lit = img > 255 * s['black']
    db_lit = seen[lit]
    want_db = (img[lit] / 255.0 - 1) * 30
    err = (db_lit - db_lit.max()) - want_db
    dark = seen[~lit] - db_lit.max()
    check('paint %s %.0f kHz: brightness = strength (dB), all %d lit pixels' % (kind, width / 1000, lit.sum()),
          np.percentile(np.abs(err - np.median(err)), 95) < 2.0,
          'error: 95 %% within %.2f dB' % np.percentile(np.abs(err - np.median(err)), 95))
    check('paint %s: black pixels stay dark (25 dB below white)' % kind, np.percentile(dark, 95) < -25,
          '95 %% of black pixels below %.1f dB' % np.percentile(dark, 95))
    check('paint %s: never clips (peak %.3f), %.2f s for 36 lines' % (kind, peak, len(z) / FS), peak <= 0.951 and
          abs(len(z) / FS - (36 * 0.1 + 0.003 + 0.25)) < 0.01)
    if kind == 'iq':
        sp = np.abs(np.fft.fft(z[:len(z) // 4096 * 4096].reshape(-1, 4096) * np.hanning(4096), axis=1)).mean(axis=0)
        fr = np.fft.fftfreq(4096, 1 / FS)
        inside = (fr >= pt.low - 100) & (fr <= pt.low + pt.width + 100)
        out = 10 * np.log10(sp[~inside & (np.abs(fr) < 15000)] ** 2 + 1e-12).max() - 10 * np.log10(sp[inside] ** 2).max()
        check('paint iq: nothing outside the picture (%.0f .. %.0f Hz)' % (pt.low, pt.low + pt.width), out < -40,
              'outside %.0f dB' % out)
inf = paint.info(200, 100, dict(paint.DEFAULT, width_hz=30000))
check('paint: the width is kept inside +-14 kHz', inf['low_hz'] >= -14000 and inf['high_hz'] <= 14000, str(inf))
pgm = os.path.join(HERE, '_test.pgm')
paint.write_pgm(pgm, paint.test_picture(30, 20))
back = paint.read_pgm(pgm)
os.remove(pgm)
check('paint: PGM written and read back', back.shape == (20, 30) and np.array_equal(back, paint.test_picture(30, 20)))

# ---------------------------------------------------------------- APRS (AX.25, AFSK 1200 baud)
fr = audio_modes.ax25_frame('N0CALL-9', 'APZARD', ['WIDE1-1'], '>Ardzy test')
check('AX.25: the frame check sequence (CRC) checks out', audio_modes.crc16(fr) == 0xF0B8)
x = audio_modes.aprs_audio('N0CALL-9', '>Ardzy test', path='WIDE1-1', fs=FS)
bits = audio_modes.afsk_demod(x, FS)
frames = audio_modes.hdlc_frames(bits)
check('APRS: the AFSK tones decode back to the frame', any(f == fr for f in frames), '%d frames found' % len(frames))
if frames:
    print('      decoded: ' + audio_modes.ax25_text(frames[0]))

# ---------------------------------------------------------------- DTMF
d = audio_modes.dtmf_audio('159#', fs=FS)
found = audio_modes.dtmf_decode(d, FS)
check('DTMF: 1 5 9 # come back', found == '159#', found)

# ---------------------------------------------------------------- WEFAX
img = np.tile(np.linspace(0, 255, 64).astype(np.uint8), (20, 1))
wf = audio_modes.Wefax(img, lpm=120, ioc=576)
check('WEFAX 120 lpm: 0.5 s a line, start 300 Hz and stop 450 Hz tones', abs(wf.line_s - 0.5) < 1e-9 and
      wf.parts[0][0] == 300 and any(p[0] == 450 for p in wf.parts))
a = np.concatenate(list(wf.words(FS)))
check('WEFAX: length start + phasing + picture + stop', abs(len(a) / FS - wf.seconds()) < 0.2,
      '%.1f s (plan %.1f s)' % (len(a) / FS, wf.seconds()))

# ---------------------------------------------------------------- SSTV
for m, info in sstv.MODES.items():
    segs = sstv.segments(sstv.test_picture(), m)
    t = sum(x[1] for x in segs)
    check('SSTV %s: %.1f s' % (info['name'], t), abs(t - info['seconds']) < 1.5, '(about %.1f s)' % info['seconds'])

print('RESULT: %d of %d ok' % (sum(results), len(results)))
