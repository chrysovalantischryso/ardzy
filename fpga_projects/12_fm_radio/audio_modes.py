"""audio_modes.py - signals the radio sends as sound (through NFM, FM, AM or USB), made on the ARM.

  APRS   AX.25 packets as 1200 baud AFSK (Bell 202: 1200 Hz mark, 2200 Hz space, NRZI, HDLC flags and
         bit stuffing, CRC-CCITT). Sent in NFM; Direwolf, multimon-ng, APRSdroid or a TNC decode it.
  DTMF   telephone key tones (two tones a key), for receivers and repeaters that react to them.
  WEFAX  radiofax pictures: 120 lines a minute, IOC 576, 1500 Hz black to 2300 Hz white, with the start
         tone (300 Hz), 30 s of phasing lines, the picture and the stop tone (450 Hz). fldigi (WEFAX),
         SDR# plugins and HamFax draw it. Sent in USB (short wave) or FM.
Every function gives FIFO words (the same sample on left and right) at the rate asked for.
"""
import math

import numpy as np


def to_words(x, level=1.0):
    v = np.clip(np.round(np.asarray(x, np.float64) * 32767 * level), -32767, 32767).astype(np.int16)
    u = v.view(np.uint16).astype(np.uint32)
    return (u << 16) | u


def fm_tone(freqs, fs, phase0=0.0):
    """A tone that follows the frequency of every sample, phase without jumps. -> (samples, last phase)."""
    ph = phase0 + np.cumsum(np.asarray(freqs, np.float64) / fs)
    return np.sin(2 * np.pi * ph), float(ph[-1] % 1.0) if len(ph) else phase0


# ---------------------------------------------------------------- AX.25 / APRS
def crc16(data):
    """CRC-CCITT as AX.25 uses it (bits LSB first, 0xFFFF start). Over a frame with its FCS: 0xF0B8."""
    c = 0xFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0x8408 if c & 1 else c >> 1
    return c


def _addr(call, last, cbit):
    call = call.upper().strip()
    name, _, ssid = call.partition('-')
    ssid = int(ssid or 0)
    if not name or len(name) > 6 or not name.isalnum() or not 0 <= ssid <= 15:
        raise ValueError('AX.25: "%s" is not a call sign (up to 6 letters and digits, -0 .. -15)' % call)
    b = bytes((ord(c) << 1) for c in name.ljust(6))
    return b + bytes(((0x80 if cbit else 0) | 0x60 | (ssid << 1) | (1 if last else 0),))


def ax25_frame(src, dest='APZARD', path=(), info=''):
    """A UI frame (what APRS uses), with its FCS. APZARD: an experimental "tocall" (AP Z = experimental)."""
    path = [p for p in path if p]
    a = _addr(dest, False, True) + _addr(src, not path, False)
    for i, p in enumerate(path):
        a += _addr(p, i == len(path) - 1, False)
    body = a + b'\x03\xf0' + info.encode('ascii', 'replace')[:256]
    f = crc16(body) ^ 0xFFFF
    return body + bytes((f & 0xFF, f >> 8))


def ax25_text(frame):
    """A frame back as text: SOURCE>DEST,PATH:info."""
    calls, i = [], 0
    while i + 7 <= len(frame):
        name = ''.join(chr(b >> 1) for b in frame[i:i + 6]).strip()
        ssid = (frame[i + 6] >> 1) & 15
        calls.append(name + ('-%d' % ssid if ssid else ''))
        last = frame[i + 6] & 1
        i += 7
        if last:
            break
    info = frame[i + 2:-2].decode('ascii', 'replace')
    return '%s>%s%s:%s' % (calls[1], calls[0], ''.join(',' + c for c in calls[2:]), info)


def hdlc_bits(frame, pre_flags=40, post_flags=4):
    """Flags, the frame bits LSB first with a 0 stuffed after five 1s, flags."""
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    out = flag * pre_flags
    ones = 0
    for byte in frame:
        for i in range(8):
            b = (byte >> i) & 1
            out.append(b)
            ones = ones + 1 if b else 0
            if ones == 5:
                out.append(0)
                ones = 0
    return out + flag * post_flags


def afsk(bits, fs, baud=1200.0, mark=1200.0, space=2200.0):
    """NRZI (a 0 changes the tone, a 1 keeps it) as continuous-phase tones."""
    tone, tones = 1, []
    for b in bits:
        if b == 0:
            tone ^= 1
        tones.append(tone)
    n = int(math.ceil(len(bits) * fs / baud))
    k = np.minimum(len(bits) - 1, (np.arange(n) * baud / fs).astype(np.intp))
    f = np.where(np.asarray(tones)[k] == 1, mark, space)
    x, _ = fm_tone(f, fs)
    return x


def aprs_audio(src, info, path='WIDE1-1', dest='APZARD', fs=48000.0, level=0.7):
    """One APRS packet as sound (with a short silence before and after)."""
    fr = ax25_frame(src, dest, [p.strip() for p in str(path).split(',') if p.strip()], info)
    x = afsk(hdlc_bits(fr), fs)
    pad = np.zeros(int(0.15 * fs))
    return np.concatenate([pad, x * level, pad])


def aprs_position(lat, lon, comment='', symbol='/-'):
    """An APRS position report without time stamp: !DDMM.mmN/DDDMM.mmE- comment."""
    la, lo = abs(float(lat)), abs(float(lon))
    s = '!%02d%05.2f%s%s%03d%05.2f%s%s%s' % (int(la), (la - int(la)) * 60, 'N' if lat >= 0 else 'S', symbol[0],
                                           int(lo), (lo - int(lo)) * 60, 'E' if lon >= 0 else 'W', symbol[1], comment)
    return s


def afsk_demod(x, fs, baud=1200.0):
    """(for the tests) bits back from AFSK made by afsk(): a tone decision per bit, then NRZI."""
    n = int(len(x) * baud / fs)
    out, prev = [], 1
    t = np.arange(int(fs / baud) + 2) / fs
    m, s = np.exp(-2j * np.pi * 1200 * t), np.exp(-2j * np.pi * 2200 * t)
    for k in range(n):
        a, b = int(round(k * fs / baud)), int(round((k + 1) * fs / baud))
        seg = x[a:b]
        tone = 1 if abs(np.dot(seg, m[:len(seg)])) > abs(np.dot(seg, s[:len(seg)])) else 0
        out.append(1 if tone == prev else 0)
        prev = tone
    return out


def hdlc_frames(bits):
    """(for the tests) frames between flags, unstuffed, with a good CRC."""
    frames, cur, ones, inside = [], [], 0, False
    for b in bits:
        if b:
            ones += 1
            cur.append(1)
            continue
        if ones == 6:                              # a flag: 0111111 0
            data = cur[:-7]                        # (the flag's own 0 and six 1s)
            if inside and len(data) >= 8 * 18 and len(data) % 8 == 0:
                fr = bytes(sum(data[i + j] << j for j in range(8)) for i in range(0, len(data), 8))
                if crc16(fr) == 0xF0B8:
                    frames.append(fr)
            cur, inside = [], True
        elif ones == 5:
            pass                                   # a stuffed 0: dropped
        else:
            cur.append(0)
        ones = 0
    return frames


# ---------------------------------------------------------------- DTMF
DTMF_ROWS = (697.0, 770.0, 852.0, 941.0)
DTMF_COLS = (1209.0, 1336.0, 1477.0, 1633.0)
DTMF_KEYS = ('123A', '456B', '789C', '*0#D')


def dtmf_audio(digits, fs=48000.0, tone_ms=100, gap_ms=100, level=0.4):
    out = [np.zeros(int(0.1 * fs))]
    t = np.arange(int(tone_ms / 1000 * fs)) / fs
    fade = np.minimum(1, np.minimum(np.arange(len(t)), np.arange(len(t))[::-1]) / (0.003 * fs))
    for d in str(digits).upper():
        if d in ' ,':
            out.append(np.zeros(int(0.5 * fs)))
            continue
        for r, keys in enumerate(DTMF_KEYS):
            if d in keys:
                c = keys.index(d)
                out.append(level * fade * (np.sin(2 * np.pi * DTMF_ROWS[r] * t) + np.sin(2 * np.pi * DTMF_COLS[c] * t)))
                out.append(np.zeros(int(gap_ms / 1000 * fs)))
    return np.concatenate(out)


def dtmf_decode(x, fs, tone_ms=100, gap_ms=100):
    """(for the tests) the keys back, at the places dtmf_audio() put them."""
    out, pos, n = '', int(0.1 * fs), int(tone_ms / 1000 * fs)
    t = np.arange(n) / fs
    while pos + n <= len(x):
        seg = x[pos:pos + n]
        if np.max(np.abs(seg)) < 0.05:
            break
        e = lambda f: abs(np.dot(seg, np.exp(-2j * np.pi * f * t)))
        r = int(np.argmax([e(f) for f in DTMF_ROWS]))
        c = int(np.argmax([e(f) for f in DTMF_COLS]))
        out += DTMF_KEYS[r][c]
        pos += n + int(gap_ms / 1000 * fs)
    return out


# ---------------------------------------------------------------- WEFAX (radiofax)
class Wefax:
    """A grey picture as radiofax sound. lpm 60, 90, 120 or 240 lines a minute; IOC 576 (or 288)."""
    BLACK, WHITE = 1500.0, 2300.0

    def __init__(self, img, lpm=120, ioc=576, phasing_s=30.0, level=0.6):
        self.img = np.asarray(img, np.uint8)
        self.lpm, self.ioc, self.level = float(lpm), int(ioc), float(level)
        self.line_s = 60.0 / self.lpm
        self.px = int(round(math.pi * self.ioc))      # 1810 dots a line at IOC 576
        start = 300 if self.ioc == 576 else 675
        n_phase = max(0, int(round(float(phasing_s) / self.line_s)))
        self.parts = [(start, 5.0), ('phasing', n_phase * self.line_s), ('picture', self.img.shape[0] * self.line_s),
                      (450, 5.0), ('black', 10.0)]

    def seconds(self):
        return sum(p[1] for p in self.parts)

    def _line_freqs(self, row, n):
        """One line (n samples) of brightness 0..255 -> frequencies."""
        x = np.interp(np.linspace(0, len(row) - 1, n), np.arange(len(row)), row.astype(np.float64))
        return self.BLACK + (self.WHITE - self.BLACK) * x / 255

    def words(self, fs, chunk_s=1.0):
        ph = 0.0
        for what, sec in self.parts:
            n_total = int(round(sec * fs))
            if what == 'phasing' or what == 'picture':
                rows = self.img if what == 'picture' else None
                n_lines = int(round(sec / self.line_s))
                done = 0
                for y in range(n_lines):
                    n = int(round((y + 1) * self.line_s * fs)) - done
                    done += n
                    if rows is None:                      # a white pulse at the start of a black line
                        row = np.zeros(200)
                        row[:10] = 255
                    else:
                        row = rows[y]
                    x, ph = fm_tone(self._line_freqs(row, n), fs, ph)
                    yield to_words(x, self.level)
                continue
            for a in range(0, n_total, int(chunk_s * fs)):
                n = min(int(chunk_s * fs), n_total - a)
                if what == 'black':
                    f = np.full(n, self.BLACK)
                else:                                     # start / stop: black and white in turn, `what` times a second
                    k = ((a + np.arange(n)) * 2 * what / fs).astype(np.int64) & 1
                    f = np.where(k == 1, self.WHITE, self.BLACK)
                x, ph = fm_tone(f, fs, ph)
                yield to_words(x, self.level)


def chunks(x, fs_unused=None, chunk=4096, level=1.0):
    """A whole signal (floats -1..1) as FIFO word chunks."""
    w = to_words(x, level)
    for i in range(0, len(w), chunk):
        yield w[i:i + chunk]
