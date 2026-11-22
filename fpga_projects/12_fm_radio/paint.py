"""paint.py - a picture in the waterfall of an SDR receiver (spectrum painting), for the Ardzy radio.

An SDR program (SDR#, SDR++, HDSDR, GQRX, a WebSDR) shows the spectrum as a waterfall: every moment a new
line of colour, one dot per frequency, brighter where the signal is stronger. If the radio sends, for a
while, many tones side by side whose strengths are the brightness of one picture line, and then the next
line, and so on, the waterfall draws the picture.

    column k of the picture   ->  a tone at  low + k * spacing  (spacing = width / (columns - 1))
    brightness of the pixel   ->  the tone's strength, in dB (a waterfall shows dB): white = 0 dB,
                                  black = -contrast dB, or silent below the black level
    each line                 ->  `line_ms` milliseconds, then the next line

Two ways to send it:
    iq    the FPGA's I/Q mode: complex samples, the picture can be up to about 28 kHz wide, centred on the
          frequency (or beside it, with the offset). No carrier, nothing else on air. Needs the new design.
    usb   as sound in USB: 300 .. 2700 Hz above the frequency (a picture 2.4 kHz wide). Works in every
          design; a USB receiver even shows it in its audio waterfall.

How it is made (cheap enough for the board's ARM): every tone sits exactly on a bin of an 8192-point
inverse FFT, so one inverse FFT per line gives a block that repeats without a seam, and the tones keep
their phase from line to line (no clicks, the picture stays sharp). Between two lines the strengths
change smoothly over `edge_ms` (a raised cosine) so the lines do not splash across the spectrum. The
tones start with Newman phases (pi k^2 / n), which keeps the peaks low, and the whole picture is scaled
once (from the loudest line), so the same brightness is the same strength in every line.
"""
import threading

import numpy as np

FS = 100e6 / 2048                 # 48828.125: the FPGA's own sound rate (no resampling at all)
NFFT = 8192                       # one bin = FS / NFFT = 5.96 Hz
BIN = FS / NFFT
IQ_EDGE = 14000.0                 # the FPGA's low-pass passes I/Q up to about +-15 kHz: keep the picture inside
USB_LOW, USB_HIGH = 300.0, 2700.0  # the side-band filter's pass band
MAX_W, MAX_H = 1024, 4096

DEFAULT = {
    'image': 'paint_image.pgm',  # the picture (grey, PGM), made by the app at the columns x lines asked for
    'kind': 'iq',                # iq or usb
    'width_hz': 20000.0,         # how wide the picture is in the waterfall
    'offset_hz': 0.0,            # where its middle is, from the frequency (iq); usb: from 300 Hz up
    'line_ms': 40.0,             # time per line (the speed)
    'contrast_db': 30.0,         # white to the darkest grey that is still sent
    'black': 0.06,               # pixels darker than this (0..1) are not sent at all
    'gamma': 1.0,                # > 1 darker middle greys, < 1 lighter
    'invert': False,             # a negative
    'mirror': False,             # left and right swapped (for an LSB receiver)
    'bottom_first': True,        # waterfalls scroll down: the last line must be sent first
    'edge_ms': 4.0,              # the soft change between two lines
    'level': 0.95,               # the loudest moment, of full scale
    'repeat_s': 0.0,             # send again after these seconds (0 = once)
    'id': 0,                     # change it to send again now
}


def read_pgm(path):
    """A binary PGM (P5, 8 bit) -> 2-D uint8 array (lines, columns)."""
    data = open(path, 'rb').read()
    parts, pos = [], 0
    while len(parts) < 4:                                # P5, width, height, maxval (comments skipped)
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':
            pos = data.index(b'\n', pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        parts.append(data[pos:end])
        pos = end
    pos += 1
    if parts[0] != b'P5':
        raise ValueError('not a binary PGM picture')
    w, h, mx = int(parts[1]), int(parts[2]), int(parts[3])
    if not (1 <= w <= MAX_W and 1 <= h <= MAX_H) or mx != 255:
        raise ValueError('the picture must be 1 .. %d x 1 .. %d, 8 bit' % (MAX_W, MAX_H))
    px = np.frombuffer(data, np.uint8, w * h, pos)
    return px.reshape(h, w)


def write_pgm(path, img):
    img = np.asarray(img, np.uint8)
    with open(path, 'wb') as f:
        f.write(b'P5\n%d %d\n255\n' % (img.shape[1], img.shape[0]))
        f.write(img.tobytes())


def layout(columns, s):
    """Where the tones go: (first bin, bins between two tones, the real width, the lowest frequency).
    The spacing is a whole number of bins (at least one), so the width may come out a little smaller."""
    kind = s.get('kind', 'iq')
    width = abs(float(s.get('width_hz', 20000)))
    if kind == 'usb':
        width = min(width, USB_HIGH - USB_LOW)
        low = USB_LOW + max(0.0, min(USB_HIGH - USB_LOW - width, float(s.get('offset_hz', 0))))
    else:
        width = min(width, 2 * IQ_EDGE)
        mid = max(-IQ_EDGE + width / 2, min(IQ_EDGE - width / 2, float(s.get('offset_hz', 0))))
        low = mid - width / 2
    step = max(1, int(width / max(1, columns - 1) / BIN)) if columns > 1 else 1
    real = step * (columns - 1) * BIN
    first = int(round((low + (width - real) / 2) / BIN))
    return first, step, real, first * BIN


def info(columns, lines, s):
    """What a picture will look like on air, for the app and the status."""
    first, step, real, low = layout(columns, s)
    line_s = max(0.002, float(s.get('line_ms', 40)) / 1000)
    return {'columns': columns, 'lines': lines, 'width_hz': round(real, 1), 'low_hz': round(low, 1),
            'high_hz': round(low + real, 1), 'spacing_hz': round(step * BIN, 2), 'line_ms': round(line_s * 1000, 2),
            'seconds': round(lines * line_s, 1), 'kind': s.get('kind', 'iq')}


class Painter:
    """Makes the sound (usb) or the I/Q samples (iq) of one picture, line by line."""

    def __init__(self, img, settings):
        s = dict(DEFAULT)
        s.update(settings or {})
        self.s = s
        img = np.asarray(img, np.uint8)
        if s['mirror']:
            img = img[:, ::-1]
        if s['bottom_first']:
            img = img[::-1]
        self.img = img
        self.lines, self.columns = img.shape
        self.kind = 'usb' if s['kind'] == 'usb' else 'iq'
        self.first, self.step, self.width, self.low = layout(self.columns, s)
        self.bins = self.first + self.step * np.arange(self.columns)
        k = np.arange(self.columns)
        self.phase = np.exp(1j * np.pi * k * k / self.columns)              # Newman phases: low peaks
        self.line_n = max(8, int(round(float(s['line_ms']) / 1000 * FS)))
        self.edge_n = max(1, min(self.line_n // 2, int(round(float(s['edge_ms']) / 1000 * FS))))
        self.scale = None
        self.error = ''
        self.ready = threading.Event()

    def amplitudes(self, row):
        b = row.astype(np.float64) / 255
        if self.s['invert']:
            b = 1 - b
        g = float(self.s['gamma'])
        if g != 1:
            b = b ** max(0.1, g)
        a = 10 ** ((b - 1) * float(self.s['contrast_db']) / 20)
        a[b < float(self.s['black'])] = 0
        return a

    def block(self, line):
        """One line as a block of NFFT samples that repeats without a seam (unscaled: a tone = amplitude)."""
        a = self.amplitudes(self.img[line]) * self.phase
        if self.kind == 'iq':
            X = np.zeros(NFFT, np.complex128)
            X[self.bins % NFFT] = a                      # (negative frequencies wrap to the top of the FFT)
            return np.fft.ifft(X) * NFFT
        X = np.zeros(NFFT // 2 + 1, np.complex128)
        X[self.bins] = a * (NFFT / 2)
        return np.fft.irfft(X, NFFT)

    def prepare(self):
        """Find the loudest line (in a thread: a few seconds for a big picture on the board)."""
        try:
            peak = 1e-9
            for y in range(self.lines):
                peak = max(peak, float(np.max(np.abs(self.block(y)))))
            self.scale = float(self.s['level']) / peak
        except Exception as e:                           # (shown in the status)
            self.error = str(e)
        self.ready.set()

    def start(self):
        threading.Thread(target=self.prepare, daemon=True).start()
        return self

    def seconds(self):
        return self.lines * self.line_n / FS + 0.3

    def words(self, chunk=4096):
        """FIFO words for the FPGA (iq: right = Q, left = I; usb: the sound on both), in chunks."""
        self.ready.wait()
        if self.error:
            raise RuntimeError(self.error)
        n0 = 0
        prev = None
        w = 0.5 - 0.5 * np.cos(np.pi * (np.arange(self.edge_n) + 0.5) / self.edge_n)   # 0 -> 1
        buf = []
        have = 0
        for y in range(self.lines + 1):
            if y < self.lines:
                cur = self.block(y) * self.scale
                n = self.line_n
            else:
                cur = np.zeros(NFFT, prev.dtype)         # the end: fade out
                n = self.edge_n
            idx = (n0 + np.arange(n)) % NFFT
            seg = cur[idx]
            e = self.edge_n
            if prev is None:
                seg[:e] *= w                             # the start: fade in
            else:
                seg[:e] = prev[idx[:e]] * (1 - w) + seg[:e] * w
            prev = cur
            n0 += n
            buf.append(seg)
            have += n
            if have >= chunk or y == self.lines:
                x = np.concatenate(buf)
                buf, have = [], 0
                yield self.pack(x)
        yield np.zeros(int(0.25 * FS), np.uint32)       # a little silence at the end

    def pack(self, x):
        if self.kind == 'iq':
            i = np.clip(np.round(x.real * 32767), -32767, 32767).astype(np.int16)
            q = np.clip(np.round(x.imag * 32767), -32767, 32767).astype(np.int16)
            return (q.view(np.uint16).astype(np.uint32) << 16) | i.view(np.uint16).astype(np.uint32)
        v = np.clip(np.round(x * 32767), -32767, 32767).astype(np.int16).view(np.uint16).astype(np.uint32)
        return (v << 16) | v


def test_picture(columns=160, lines=120):
    """A frame, a diagonal, a grey ramp and the word ARDZY: shows at once if the picture comes out right."""
    import font
    img = np.zeros((lines, columns), np.uint8)
    img[0, :] = img[-1, :] = 255
    img[:, 0] = img[:, -1] = 255
    for x in range(columns):
        img[lines - 1 - (x * (lines - 1)) // (columns - 1), x] = 200
    ramp = np.linspace(40, 255, columns - 8).astype(np.uint8)
    img[lines - 14:lines - 6, 4:columns - 4] = ramp
    text = font.render('ARDZY', scale=max(1, columns // 40))
    th, tw = text.shape
    y0, x0 = max(2, lines // 4 - th // 2), max(2, (columns - tw) // 2)
    sub = img[y0:y0 + th, x0:x0 + tw]
    sub[...] = np.maximum(sub, text[:sub.shape[0], :sub.shape[1]] * 255)
    return img


if __name__ == '__main__':                               # a check on the PC: paint, then look with an FFT
    img = test_picture(64, 48)
    s = dict(DEFAULT, width_hz=12000, line_ms=20, edge_ms=2)
    p = Painter(img, s).start()
    x = np.concatenate(list(p.words()))
    i = (x & 0xFFFF).astype(np.uint16).view(np.int16).astype(np.float64)
    q = (x >> 16).astype(np.uint16).view(np.int16).astype(np.float64)
    z = i + 1j * q
    print('picture %d x %d, %.1f s, %s' % (img.shape[1], img.shape[0], len(z) / FS, info(64, 48, s)))
