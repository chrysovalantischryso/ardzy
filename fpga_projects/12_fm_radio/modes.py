"""modes.py - signals for the radio's symbol player, and audio files for the FM transmitter.

A symbol is (carrier offset in Hz, time in microseconds, width 0..512, phase 0..255): the FPGA sends
the carrier at that offset, that strong, for that long, then takes the next symbol. That is enough for
  CW     Morse code: the carrier keyed on and off (with soft edges, so no clicks)
  RTTY   radio teletype: two tones 170 Hz apart, 45.45 baud, the Baudot (ITA2) code
  PSK    BPSK31, 63, 125 or 250: phase reversals with the varicode alphabet, as in the program fldigi
  QRSS   very slow Morse (a dot of 3, 10 or more seconds), read on a waterfall; DFCW: dots and dashes
         the same length on two frequencies
  Hell   Feld-Hellschreiber: the text is scanned like a fax, 7 x 14 dots a letter, 122.5 dots a second (0.8 s a letter);
         fldigi (and the eye, on a slow waterfall) reads it
  WSPR   a weak-signal beacon: call sign, locator and power in 4 tones 1.46 Hz apart, 110.6 s, starting
         one second after an even minute; WSJT-X decodes it and reports it to wsprnet.org
  beacon a melody or a tone sequence for receivers in SSB / CW mode
  sweep  the carrier stepping across a range, to test filters and antennas
Listen with an SDR (an RTL-SDR with SDR# or SDR++) in USB mode, 1 kHz below the carrier, and decode
RTTY, PSK and Hell with fldigi, WSPR with WSJT-X.
"""
import array
import math
import sys
import wave

FULL = 512


def width_for(level):
    """Carrier strength 0..1 -> pulse width (the strength of a 1-bit carrier is sin(pi * width / 1024))."""
    return round(1024 * math.asin(max(0.0, min(1.0, level))) / math.pi)


# ---------------------------------------------------------------- CW (Morse code)
MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.', 'H': '....',
    'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 'P': '.--.',
    'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.', '.': '.-.-.-', ',': '--..--',
    '?': '..--..', "'": '.----.', '!': '-.-.--', '/': '-..-.', '(': '-.--.', ')': '-.--.-', '&': '.-...',
    ':': '---...', ';': '-.-.-.', '=': '-...-', '+': '.-.-.', '-': '-....-', '_': '..--.-', '"': '.-..-.',
    '$': '...-..-', '@': '.--.-.',
}


def cw(text, wpm=15, offset_hz=0.0, edge_ms=4, level=1.0):
    """Morse code. A dot is 1.2 / wpm seconds; dash 3 dots, gaps 1 / 3 / 7 dots.
    Every key-down rises and falls over edge_ms (a raised cosine) so the signal stays narrow."""
    dot = 1.2e6 / wpm
    steps = max(1, int(edge_ms))
    edge = [width_for(level * math.sin(math.pi / 2 * (k + 0.5) / steps) ** 2) for k in range(steps)]
    out = []

    def key(n_dots):
        flat = n_dots * dot - 2 * steps * 1000
        for w in edge:
            out.append((offset_hz, 1000, w, 0))
        out.append((offset_hz, max(1, flat), width_for(level), 0))
        for w in reversed(edge):
            out.append((offset_hz, 1000, w, 0))

    def space(n_dots):
        out.append((offset_hz, n_dots * dot, 0, 0))

    for word in text.upper().split():
        for i, ch in enumerate(word):
            code = MORSE.get(ch)
            if not code:
                continue
            for j, el in enumerate(code):
                key(1 if el == '.' else 3)
                if j < len(code) - 1:
                    space(1)
            space(3)
        space(4)                                   # 3 + 4 = 7 dots between words
    return out


# ---------------------------------------------------------------- RTTY (Baudot / ITA2)
_LTRS = '\0E\nA SIU\rDRJNFCKTZLWHYPQOBG\0MXV\0'
_FIGS = {'3': 1, '-': 3, "'": 5, '8': 6, '7': 7, '4': 10, ',': 12, ':': 14, '(': 15, '5': 16, '+': 17,
         ')': 18, '2': 19, '6': 21, '0': 22, '1': 23, '9': 24, '?': 25, '.': 28, '/': 29, '=': 30}
LTRS, FIGS = 31, 27


def rtty(text, baud=45.45, shift=170.0, offset_hz=0.0, level=1.0):
    """RTTY: 1 start bit (space), 5 data bits (first bit first sent), 1.5 stop bits (mark).
    Mark is the higher tone (+shift/2), as fldigi expects in USB."""
    bit = 1e6 / baud
    w = width_for(level)
    mark, spc = offset_hz + shift / 2, offset_hz - shift / 2
    out = [(mark, 500000, w, 0)]                   # half a second of idle mark first

    def char(code):
        out.append((spc, bit, w, 0))
        for i in range(5):
            out.append((mark if code >> i & 1 else spc, bit, w, 0))
        out.append((mark, 1.5 * bit, w, 0))

    shift_state = None
    char(LTRS)
    char(LTRS)
    for ch in text.upper():
        if ch == '\n':
            char(8)                                # CR, LF
            char(2)
            continue
        if ch in _LTRS and ch not in '\0':
            if shift_state != 'L' and ch not in ' \r\n':
                char(LTRS)
                shift_state = 'L'
            char(_LTRS.index(ch))
        elif ch in _FIGS:
            if shift_state != 'F':
                char(FIGS)
                shift_state = 'F'
            char(_FIGS[ch])
    char(8)
    char(2)
    out.append((mark, 300000, w, 0))
    return out


# ---------------------------------------------------------------- PSK31 (G3PLX)
VARICODE = [
    '1010101011', '1011011011', '1011101101', '1101110111', '1011101011', '1101011111', '1011101111', '1011111101',
    '1011111111', '11101111', '11101', '1101101111', '1011011101', '11111', '1101110101', '1110101011',
    '1011110111', '1011110101', '1110101101', '1110101111', '1101011011', '1101101011', '1101101101', '1101010111',
    '1101111011', '1101111101', '1110110111', '1101010101', '1101011101', '1110111011', '1011111011', '1101111111',
    '1', '111111111', '101011111', '111110101', '111011011', '1011010101', '1010111011', '101111111',
    '11111011', '11110111', '101101111', '111011111', '1110101', '110101', '1010111', '110101111',
    '10110111', '10111101', '11101101', '11111111', '101110111', '101011011', '101101011', '110101101',
    '110101011', '110110111', '11110101', '110111101', '111101101', '1010101', '111010111', '1010101111',
    '1010111101', '1111101', '11101011', '10101101', '10110101', '1110111', '11011011', '11111101',
    '101010101', '1111111', '111111101', '101111101', '11010111', '10111011', '11011101', '10101011',
    '11010101', '111011101', '10101111', '1101111', '1101101', '101010111', '110110101', '101011101',
    '101110101', '101111011', '1010101101', '111110111', '111101111', '111111011', '1010111111', '101101101',
    '1011011111', '1011', '1011111', '101111', '101101', '11', '111101', '1011011',
    '101011', '1101', '111101011', '10111111', '11011', '111011', '1111', '111',
    '111111', '110111111', '10101', '10111', '101', '110111', '1111011', '1101011',
    '11011111', '1011101', '111010101', '1010110111', '110111011', '1010110101', '1011010111', '1110110101',
]


def psk31_bits(text):
    bits = '0' * 32                                # preamble: phase reversals for the receiver to lock
    for ch in text:
        c = ord(ch)
        if c < 128:
            bits += VARICODE[c] + '00'
    return bits + '1' * 32                         # postamble: steady carrier


def psk31(text, offset_hz=0.0, level=1.0, steps=8, baud=31.25):
    """BPSK at 31.25 baud (or 62.5, 125, 250: PSK63, PSK125, PSK250): a 0 bit reverses the phase, a 1
    keeps it. During a reversal the amplitude follows a cosine through zero (that keeps the signal as
    narrow as the baud rate), shaped here in `steps` parts. The preamble lasts about a second at every speed."""
    T = round(1e6 / float(baud))                   # microseconds per bit
    extra = max(0, int(round(float(baud) / 31.25)) - 1) * 32
    out, phase = [], 0
    full = width_for(level)
    for b in '0' * extra + psk31_bits(text) + '1' * extra:
        if b == '1':
            out.append((offset_hz, T, full, phase))
        else:
            for k in range(steps):
                a = math.cos(math.pi * (k + 0.5) / steps)
                ph = phase if a >= 0 else (phase + 128) & 255
                out.append((offset_hz, T // steps, width_for(level * abs(a)), ph))
            phase = (phase + 128) & 255
    out.append((offset_hz, 1000, 0, 0))
    return out


# ---------------------------------------------------------------- beacon, sweep
NOTES = {'C': -9, 'D': -7, 'E': -5, 'F': -4, 'G': -2, 'A': 0, 'B': 2}


def note_hz(name):
    """'A4' = 440 Hz, 'C#5', 'Bb3' ..."""
    n = NOTES[name[0].upper()]
    rest = name[1:]
    if rest[:1] == '#':
        n, rest = n + 1, rest[1:]
    elif rest[:1] == 'b':
        n, rest = n - 1, rest[1:]
    octave = int(rest or 4)
    return 440.0 * 2 ** ((n + 12 * (octave - 4)) / 12)


def beacon(melody, base_hz=0.0, tempo=120, level=1.0):
    """A melody for SSB / CW receivers: each note moves the carrier, so the receiver plays it as a tone.
    melody: 'C4 E4 G4 C5/2 - G4' (/2 = half note, *2 = double, - = rest)."""
    beat = 60e6 / tempo
    out = []
    for tok in melody.split():
        length = 1.0
        if '/' in tok:
            tok, d = tok.split('/')
            length = 1 / float(d)
        elif '*' in tok:
            tok, m = tok.split('*')
            length = float(m)
        us = beat * length
        if tok == '-':
            out.append((base_hz, us, 0, 0))
        else:
            out.append((base_hz + note_hz(tok), us * 0.9, width_for(level), 0))
            out.append((base_hz, us * 0.1, 0, 0))
    return out


def sweep(start_hz, stop_hz, step_hz, dwell_ms=50, level=1.0):
    """The carrier steps from start to stop (offsets, within +-970 kHz of the carrier)."""
    n = max(1, int(abs(stop_hz - start_hz) / abs(step_hz)))
    return [(start_hz + (stop_hz - start_hz) * i / n, dwell_ms * 1000, width_for(level), 0) for i in range(n + 1)]


PSK_BAUDS = {'psk31': 31.25, 'psk63': 62.5, 'psk125': 125.0, 'psk250': 250.0}


# ---------------------------------------------------------------- QRSS / DFCW (slow Morse for waterfalls)
def qrss(text, dot_s=3.0, offset_hz=0.0, dfcw_hz=0.0, edge_ms=200, level=1.0):
    """Morse so slow that it is read on a waterfall instead of by ear (QRSS 3: a dot of 3 s).
    dfcw_hz = 0: the usual on / off keying. dfcw_hz > 0 (DFCW): every element is one dot long, a dash is
    dfcw_hz higher than a dot, with a short gap between the elements: twice as fast for the same dot."""
    if dfcw_hz <= 0:
        return cw(text, wpm=1.2 / max(0.05, float(dot_s)), offset_hz=offset_hz, edge_ms=edge_ms, level=level)
    dot = float(dot_s) * 1e6
    w = width_for(level)
    out = []
    for word in text.upper().split():
        for ch in word:
            code = MORSE.get(ch)
            if not code:
                continue
            for el in code:
                out.append((offset_hz + (dfcw_hz if el == '-' else 0.0), dot, w, 0))
                out.append((offset_hz, dot / 3, 0, 0))
            out.append((offset_hz, dot, 0, 0))
        out.append((offset_hz, 2 * dot, 0, 0))
    return out


# ---------------------------------------------------------------- Feld-Hellschreiber
HELL_BAUD = 122.5                                  # dots per second (a letter: 7 columns x 14 dots = 0.8 s)


def hell(text, offset_hz=0.0, level=1.0, edge_us=800, wide=False):
    """Feld Hell: each letter is 7 columns of 14 dots (the 5 x 7 font with every row doubled, and 2 empty
    columns), a column is sent from the bottom up, the carrier is on for ink and off for paper. The receiver
    (fldigi in Feld Hell, or a slow waterfall) draws the columns side by side. wide: every column twice."""
    import font
    px = 1e6 / HELL_BAUD
    w = width_for(level)
    steps = 4
    edge = [width_for(level * math.sin(math.pi / 2 * (k + 0.5) / steps) ** 2) for k in range(steps)]
    seq = []                                       # dots, on (1) or off (0), in sending order
    for ch in ' ' + text + ' ':
        g = font.glyph(ch)                         # 7 rows x 5 columns, top row first
        for c in range(7):
            dots = [int(g[r // 2, c]) for r in range(14)] if c < 5 else [0] * 14
            for _ in range(2 if wide else 1):
                seq += dots[::-1]                  # (from the bottom up)
    out, i = [], 0
    eu = min(float(edge_us), px / 2) / steps
    while i < len(seq):                            # runs of the same dot, soft edges on the ink
        j = i
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        t = (j - i) * px
        if seq[i]:
            out += [(offset_hz, eu, e, 0) for e in edge]
            out.append((offset_hz, max(1.0, t - 2 * steps * eu), w, 0))
            out += [(offset_hz, eu, e, 0) for e in reversed(edge)]
        else:
            out.append((offset_hz, t, 0, 0))
        i = j
    return out


# ---------------------------------------------------------------- WSPR
WSPR_SYNC = [int(c) for c in (
    '110000001000111000100101111000000010010100000010110011010001101000011010101010010010110001101010001'
    '000001001001110110011010001110000010100110000000110101100011000')]
WSPR_SPACING = 12000 / 8192                        # 1.4648 Hz between the 4 tones
WSPR_SYMBOL_US = 8192 / 12000 * 1e6                # 0.6827 s a symbol, 162 symbols = 110.6 s
WSPR_POWERS = (0, 3, 7, 10, 13, 17, 20, 23, 27, 30, 33, 37, 40, 43, 47, 50, 53, 57, 60)


def _wspr_char(c):
    if c.isdigit():
        return ord(c) - 48
    if 'A' <= c <= 'Z':
        return ord(c) - 55
    return 36                                      # space


def wspr_check(call, locator, dbm):
    """'' when the message can be sent, else what is wrong with it."""
    call, loc = str(call).strip().upper(), str(locator).strip().upper()
    if not 3 <= len(call) <= 6 or not all(c.isalnum() for c in call):
        return 'the call sign must be 3 to 6 letters and digits (no / and no extensions in this form)'
    c = (' ' + call) if call[1].isdigit() else call
    if len(c) > 6 or not c[2].isdigit() or any(x.isdigit() for x in c[3:]):
        return 'a call sign like K1ABC, DL1AB or SV1ABC: a digit as its 2nd or 3rd character, then up to 3 letters'
    if len(loc) != 4 or not ('A' <= loc[0] <= 'R' and 'A' <= loc[1] <= 'R' and loc[2:].isdigit()):
        return 'the locator is 4 characters, like KM17 or JN58'
    try:
        if int(dbm) not in WSPR_POWERS:
            raise ValueError
    except (TypeError, ValueError):
        return 'the power in dBm must be one of %s' % ', '.join(map(str, WSPR_POWERS))
    return ''


def wspr_symbols(call, locator, dbm):
    """The 162 channel symbols (0..3) of a WSPR message type 1 (call sign, 4-character locator, dBm)."""
    err = wspr_check(call, locator, dbm)
    if err:
        raise ValueError('WSPR: ' + err)
    call, loc = call.strip().upper(), locator.strip().upper()
    if call[1].isdigit():
        call = ' ' + call
    call = (call + '      ')[:6]
    n = _wspr_char(call[0])
    n = n * 36 + _wspr_char(call[1])
    n = n * 10 + _wspr_char(call[2])
    for c in call[3:]:
        n = n * 27 + (_wspr_char(c) - 10)
    m = (179 - 10 * (ord(loc[0]) - 65) - int(loc[2])) * 180 + 10 * (ord(loc[1]) - 65) + int(loc[3])
    m = m * 128 + int(dbm) + 64
    bits = [(n >> (27 - i)) & 1 for i in range(28)] + [(m >> (21 - i)) & 1 for i in range(22)] + [0] * 31
    reg, coded = 0, []                             # convolutional code, K = 32, rate 1/2
    for b in bits:
        reg = ((reg << 1) | b) & 0xFFFFFFFF
        coded.append(bin(reg & 0xF2D05351).count('1') & 1)
        coded.append(bin(reg & 0xE4613C47).count('1') & 1)
    inter, p = [0] * 162, 0                        # interleaving by bit-reversed addresses
    for i in range(256):
        j = int('{:08b}'.format(i)[::-1], 2)
        if j < 162:
            inter[j] = coded[p]
            p += 1
    return [WSPR_SYNC[i] + 2 * inter[i] for i in range(162)]


def wspr(call, locator, dbm, offset_hz=1500.0, level=1.0):
    """The WSPR transmission as symbols: tone k at offset + (k - 1.5) * 1.4648 Hz (about 6 Hz wide)."""
    w = width_for(level)
    base = offset_hz - 1.5 * WSPR_SPACING
    return [(base + s * WSPR_SPACING, WSPR_SYMBOL_US, w, 0) for s in wspr_symbols(call, locator, dbm)] + \
           [(offset_hz, 1000, 0, 0)]


def wspr_next_start(now):
    """The next WSPR slot start: one second after an even minute (UTC), not before now."""
    t = math.floor(now / 120.0) * 120 + 1
    while t < now:
        t += 120
    return t


# ---------------------------------------------------------------- timing
def quantize(symbols, max_us=1000000):
    """Whole microseconds for the FPGA, with the rounding carried on (no drift over a long message),
    and symbols longer than the FPGA takes (about 1 s) cut into parts."""
    out, t, done = [], 0.0, 0
    for off, us, w, ph in symbols:
        t += us
        n = int(round(t)) - done
        done += n
        while n > max_us:
            out.append((off, max_us, w, ph))
            n -= max_us
        if n > 0:
            out.append((off, n, w, ph))
    return out


def duration_s(symbols):
    return sum(s[1] for s in symbols) / 1e6


# ---------------------------------------------------------------- audio files
def wav_info(path):
    with wave.open(path, 'rb') as w:
        return {'rate': w.getframerate(), 'channels': w.getnchannels(), 'bits': 8 * w.getsampwidth(),
                'seconds': w.getnframes() / max(1, w.getframerate())}


def wav_words(path, chunk=4096):
    """Yield lists of FIFO words (right << 16 | left) from a PCM WAV file (8, 16, 24 or 32 bit, mono or stereo)."""
    with wave.open(path, 'rb') as w:
        ch, sw = w.getnchannels(), w.getsampwidth()
        if sw not in (1, 2, 3, 4) or ch < 1:
            raise ValueError('only PCM WAV files (8, 16, 24 or 32 bit)')
        while True:
            data = w.readframes(chunk)
            if not data:
                return
            if sw == 2 and ch == 2 and sys.byteorder == 'little':
                # 16-bit stereo: the bytes L, R already are the FIFO word R << 16 | L
                a = array.array('I')
                a.frombytes(data[:len(data) // 4 * 4])
                yield a.tolist()
                continue
            if sw == 2 and ch == 1 and sys.byteorder == 'little':
                a = array.array('H')
                a.frombytes(data[:len(data) // 2 * 2])
                yield [v * 0x10001 for v in a]
                continue
            n = len(data) // (sw * ch)
            out = []
            for i in range(n):
                base = i * sw * ch
                vals = []
                for c in range(min(ch, 2)):
                    o = base + c * sw
                    if sw == 1:
                        v = (data[o] - 128) << 8
                    else:
                        v = int.from_bytes(data[o + sw - 2:o + sw], 'little', signed=True)
                    vals.append(v)
                l = vals[0]
                r = vals[1] if len(vals) > 1 else l
                out.append(((r & 0xFFFF) << 16) | (l & 0xFFFF))
            yield out


if __name__ == '__main__':                      # checks on a PC
    for i, c in enumerate(VARICODE):
        assert c[0] == '1' and c[-1] == '1' and '00' not in c, (i, c)
    assert len(set(VARICODE)) == 128
    print('varicode ok; CW "CQ" %.2f s, RTTY "RYRY" %.2f s, PSK31 "cq cq" %.2f s, A4 = %.1f Hz' % (
        duration_s(cw('CQ', 20)), duration_s(rtty('RYRY')), duration_s(psk31('cq cq')), note_hz('A4')))
