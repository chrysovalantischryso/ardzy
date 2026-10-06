"""Decodes the symbol lists of fpga_projects/12_fm_radio/modes.py back to text, with decoders written
from the protocol rules (not from the encoders): CW, RTTY (Baudot), PSK31 (varicode).

    python modes_decode_test.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'fpga_projects', '12_fm_radio'))
import modes  # noqa: E402

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-44s %s' % ('ok' if ok else 'FAIL', name, detail))


def timeline(symbols):
    t, out = 0.0, []
    for off, us, width, ph in symbols:
        out.append((t, t + us, off, width, ph))
        t += us
    return out


def at(tl, t):
    for a, b, off, width, ph in tl:
        if a <= t < b:
            return off, width, ph
    return None


# ---------------------------------------------------------------- CW
MORSE_BACK = {v: k for k, v in modes.MORSE.items()}


def cw_decode(symbols, wpm):
    dot = 1.2e6 / wpm
    runs = []                                   # (on, duration) merged
    for off, us, width, ph in symbols:
        on = width > modes.width_for(0.5)       # above half strength = key down (the edges are soft)
        if runs and runs[-1][0] == on:
            runs[-1][1] += us
        else:
            runs.append([on, us])
    text, letter = '', ''
    for on, d in runs:
        if on:
            letter += '.' if d < 2 * dot else '-'
        else:
            if d > 5 * dot:
                text += MORSE_BACK.get(letter, '?') + ' '
                letter = ''
            elif d > 2 * dot:
                text += MORSE_BACK.get(letter, '?')
                letter = ''
    if letter:
        text += MORSE_BACK.get(letter, '?')
    return text.strip()


msg = 'CQ CQ DE ARDZY 73'
check('CW decodes back', cw_decode(modes.cw(msg, 20), 20) == msg, repr(cw_decode(modes.cw(msg, 20), 20)))

# ---------------------------------------------------------------- RTTY
ITA2_L = {0: '', 1: 'E', 2: '\n', 3: 'A', 4: ' ', 5: 'S', 6: 'I', 7: 'U', 8: '\r', 9: 'D', 10: 'R', 11: 'J', 12: 'N',
          13: 'F', 14: 'C', 15: 'K', 16: 'T', 17: 'Z', 18: 'L', 19: 'W', 20: 'H', 21: 'Y', 22: 'P', 23: 'Q', 24: 'O',
          25: 'B', 26: 'G', 28: 'M', 29: 'X', 30: 'V'}
ITA2_F = {1: '3', 2: '\n', 3: '-', 4: ' ', 5: "'", 6: '8', 7: '7', 8: '\r', 10: '4', 12: ',', 14: ':', 15: '(',
          16: '5', 17: '+', 18: ')', 19: '2', 21: '6', 22: '0', 23: '1', 24: '9', 25: '?', 28: '.', 29: '/', 30: '='}


def rtty_decode(symbols, baud=45.45):
    tl = timeline(symbols)
    end = tl[-1][1]
    bit = 1e6 / baud
    mark = lambda t: at(tl, t)[0] > 0
    t, text, figs = 0.0, '', False
    while t < end - 7 * bit:
        if mark(t):
            t += bit / 16
            continue
        # a start bit begins at t: sample the data bits in their middle
        code = sum((1 << i) for i in range(5) if mark(t + (1.5 + i) * bit))
        if not mark(t + 6.5 * bit):
            text += '#'                         # no stop bit: framing error
        if code == 31:
            figs = False
        elif code == 27:
            figs = True
        else:
            text += (ITA2_F if figs else ITA2_L).get(code, '?')
        t += 7.4 * bit
    return text.replace('\r', '').strip()


msg = 'CQ CQ DE ARDZY, RST 599 (TEST) 73'
got = rtty_decode(modes.rtty(msg))
check('RTTY decodes back (Baudot, letters and figures)', got == msg, repr(got))

# ---------------------------------------------------------------- PSK31
VARI_BACK = {c: chr(i) for i, c in enumerate(modes.VARICODE)}


def psk31_decode(symbols):
    tl = timeline(symbols)
    T = 32000
    n = int(tl[-1][1] // T)
    bits, prev = '', None
    for k in range(n):
        s = at(tl, (k + 1) * T - 10)            # the phase at the end of each bit
        if s is None:
            break
        ph = s[2]
        if prev is not None:
            bits += '1' if ph == prev else '0'
        prev = ph
    text = ''
    for part in bits.split('00'):
        part = part.strip('0')
        if part in VARI_BACK:
            text += VARI_BACK[part]
    return text


msg = 'cq cq de Ardzy: PSK31 test 1234 @ 73!'
got = psk31_decode(modes.psk31(msg))
check('PSK31 decodes back (varicode, phase reversals)', msg in got, repr(got))
# the shaping: during a reversal the strength goes through zero, else it stays full
s = modes.psk31('e')
widths = sorted({w for _, _, w, _ in s})
check('PSK31 reversals pass through zero strength', widths[0] < modes.width_for(0.25) and widths[-1] == modes.width_for(1.0),
      'widths %d .. %d' % (widths[0], widths[-1]))

print('RESULT: %d of %d ok' % (sum(results), len(results)))
