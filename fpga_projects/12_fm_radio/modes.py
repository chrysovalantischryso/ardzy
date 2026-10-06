"""modes.py - signals for the radio's symbol player, and audio files for the FM transmitter.

A symbol is (carrier offset in Hz, time in microseconds, width 0..512, phase 0..255): the FPGA sends
the carrier at that offset, that strong, for that long, then takes the next symbol. That is enough for
  CW     Morse code: the carrier keyed on and off (with soft edges, so no clicks)
  RTTY   radio teletype: two tones 170 Hz apart, 45.45 baud, the Baudot (ITA2) code
  PSK31  phase reversals at 31.25 baud with the varicode alphabet, as in the program fldigi
  beacon a melody or a tone sequence for receivers in SSB / CW mode
  sweep  the carrier stepping across a range, to test filters and antennas
Listen with an SDR (an RTL-SDR with SDR# or SDR++) in USB mode, 1 kHz below the carrier, and decode
RTTY and PSK31 with fldigi.
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


def psk31(text, offset_hz=0.0, level=1.0, steps=8):
    """BPSK at 31.25 baud: a 0 bit reverses the phase, a 1 keeps it. During a reversal the amplitude
    follows a cosine through zero (that keeps the signal 31 Hz wide), shaped here in `steps` parts."""
    T = 32000                                      # microseconds per bit
    out, phase = [], 0
    full = width_for(level)
    for b in psk31_bits(text):
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
