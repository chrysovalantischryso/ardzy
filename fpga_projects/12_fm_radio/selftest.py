# 12 FM radio self-test. Everything is measured, nothing is taken on trust:
#   the MPX signal captured inside the FPGA (levels, pilot, stereo separation decoded back, the 15 kHz
#   filter, pre-emphasis, the RDS waveform demodulated), the RDS data decoded back to the station name,
#   the carrier counted at the pin (frequency, FM deviation, AM, the symbol player), the audio resampler.
# The RF checks send for a few seconds on 27.12 and 40.68 MHz (ISM frequencies), with no antenna.
import cmath
import math
import time
from blocks import Bus, Radio, require, tone_level
import rds

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-52s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def near(v, want, tol):
    return abs(v - want) <= tol


bus = Bus()
require(bus, 'FMTX')
r = Radio(bus, slot=1)
FS = r.FS_MPX
check('radio block answers, 250 MHz RF clock locked', r.ok() and r.locked())

# ---------------------------------------------------------------- 1. the MPX signal, test tones
r.mode('off')
r.levels()
r.volume(1.0)
r.setup(tx=False, stereo=True, rds=False, pilot=True, preemph=0, mute=False, tones=True)
r.tones(1000, 0)                     # left 1 kHz at half scale, right silent
time.sleep(0.05)
x = r.capture()
m1 = tone_level(x, 1000, FS, True)
pil = tone_level(x, 19000, FS, True)
want_m = 0.87 * 16383 / 2            # A * M, M = (L + R) / 2
check('1 kHz in the MPX (87 % of half of the left tone)', near(abs(m1), want_m, want_m * 0.03), '%.0f (want %.0f)' % (abs(m1), want_m))
check('19 kHz pilot at 9 %', near(abs(pil), 2949, 60), '%.0f (want 2949)' % abs(pil))
sb = (tone_level(x, 37000, FS) + tone_level(x, 39000, FS)) / 2
c38 = tone_level(x, 38000, FS)
check('stereo: 37 + 39 kHz side bands, no 38 kHz carrier', near(sb, want_m / 2, want_m * 0.03) and c38 < 30,
      'side bands %.0f (want %.0f), 38 kHz %.0f' % (sb, want_m / 2, c38))
# decode left and right back: the 38 kHz carrier is sin(2p) where the pilot is sin(p)
psi = cmath.phase(pil)               # pilot = |pil| cos(w n + psi) = sin(w n + psi + pi/2)
w = 2 * math.pi * 19000.0007 / FS
s_bb = [v * 2 * math.sin(2 * (w * n + psi + math.pi / 2)) for n, v in enumerate(x)]
s1 = tone_level(s_bb, 1000, FS, True)
left, right = abs(m1 + s1), abs(m1 - s1)
sep = 20 * math.log10(left / max(right, 1e-3))
check('stereo decoded back: left only, right silent', sep > 40, 'separation %.1f dB' % sep)

r.setup(stereo=False)
time.sleep(0.02)
x = r.capture()
check('mono: no pilot, no 38 kHz side bands', tone_level(x, 19000, FS) < 10 and tone_level(x, 39000, FS) < 10,
      'pilot %.1f, 39 kHz %.1f' % (tone_level(x, 19000, FS), tone_level(x, 39000, FS)))

r.tones(10000, 0)
time.sleep(0.02)
a10 = tone_level(r.capture(), 10000, FS)
r.tones(19500, 0)
time.sleep(0.02)
a195 = tone_level(r.capture(), 19500, FS)
check('15 kHz low-pass: 10 kHz passes, 19.5 kHz blocked', near(a10, want_m, want_m * 0.05) and a195 < want_m * 0.001,
      '10 kHz %.0f, 19.5 kHz %.2f (%.0f dB)' % (a10, a195, 20 * math.log10(max(a195, 1e-3) / want_m)))

r.tones(3000, 0)
r.setup(preemph=50)
time.sleep(0.02)
a3p = tone_level(r.capture(), 3000, FS)
r.setup(preemph=0)
time.sleep(0.02)
a3 = tone_level(r.capture(), 3000, FS)
wd = 2 * math.pi * 3000 / r.FS_AUDIO
gain = abs(1 + 625 / 256 * (1 - cmath.exp(-1j * wd)))
check('pre-emphasis 50 us: 3 kHz louder', near(a3p / a3, gain, 0.03), 'x%.3f (want x%.3f)' % (a3p / a3, gain))

r.tones(1000, 0)
r.peaks()
time.sleep(0.05)
pk = r.peaks()
check('level meters: left half scale, right silent', near(pk['left'], 0.5, 0.01) and pk['right'] < 0.01,
      'left %.3f, right %.3f' % (pk['left'], pk['right']))

# ---------------------------------------------------------------- 2. RDS
st = rds.Station(pi=0xA5D1, ps='SELFTEST', rt='Ardzy radio self-test, RDS text', pty=4, ct=False)
on_air, _ = r.rds_bank()
r.rds_load(st.cycle(), 1 - on_air)
t = time.time()
while r.rds_bank()[0] != 1 - on_air and time.time() - t < 6:
    time.sleep(0.05)
check('RDS bank change-over at the end of the round', r.rds_bank()[0] == 1 - on_air)
r.setup(stereo=True, rds=True, mute=True)
time.sleep(0.05)
x = r.capture()
# the RDS waveform: demodulate with sin(3p), then each bit should be one clean +-sine period
pil = tone_level(x, 19000, FS, True)
psi = cmath.phase(pil)
d = [v * 2 * math.sin(3 * (w * n + psi + math.pi / 2)) for n, v in enumerate(x)]
T = FS / 1187.5
best = (0, 0, [])
for start in range(0, int(T), 4):
    corr = []
    k = 0
    while start + (k + 1) * T <= len(d):
        a, b = int(round(start + k * T)), int(round(start + (k + 1) * T))
        corr.append(sum(d[n] * math.sin(2 * math.pi * (n - start - k * T) / T) for n in range(a, b)))
        k += 1
    q = sum(abs(c) for c in corr)
    if q > best[0]:
        best = (q, start, corr)
expect = 1311 / 32768 * 32767 * T / 2
quality = [abs(c) / expect for c in best[2]]
check('RDS signal: %d bits, each a clean biphase symbol' % len(quality), min(quality) > 0.85 and max(quality) < 1.15,
      'size %.2f .. %.2f of the ideal' % (min(quality), max(quality)))
c57 = tone_level(x, 57000, FS)
check('RDS: no 57 kHz carrier left (biphase)', c57 < 0.05 * 1311, '%.1f (%.0f dB below the RDS level)' % (c57, 20 * math.log10(1311 / max(c57, 1e-3))))

r.rds_log_clear()
bits, t0 = [], time.time()
while time.time() - t0 < 3.0:
    time.sleep(0.3)
    bits += r.rds_log()
rate = len(bits) / (time.time() - t0)
check('RDS bit rate 1187.5 per second', near(rate, 1187.5, 60), '%.0f bits/s' % rate)
dec = rds.decode(bits)
check('RDS decoded back: station name', dec['ps'] == 'SELFTEST', repr(dec['ps']))
check('RDS decoded back: PI code, programme type, text',
      dec['pi'] == 0xA5D1 and dec['pty'] == 4 and dec['rt'] == st.rt,
      'PI %s, PTY %s, %d groups, text %r' % (('%04X' % dec['pi']) if dec['pi'] is not None else None, dec['pty'], dec['groups'], dec['rt']))
r.setup(rds=False, mute=False)

# ---------------------------------------------------------------- 3. the carrier at the pin
F1 = 27.12e6
r.frequency(F1)
r.power(1.0, key=True)
r.setup(tx=True, tones=False, stereo=False, rds=False, preemph=0)
r.mode('carrier')
time.sleep(0.3)
hz = r.rf_hz()
check('carrier 27.12 MHz counted at the pin', near(hz, F1, 20), '%d Hz' % hz)
r.frequency(40.68e6)
time.sleep(0.3)
hz = r.rf_hz()
check('carrier 40.68 MHz counted at the pin', near(hz, 40.68e6, 20), '%d Hz' % hz)
r.frequency(F1)

# FM: steady audio moves the carrier by (0.87 * level * 75 kHz)
r.deviation(75000)
r.input_rate(3052)
r.mode('fm')
for level in (16384, -16384):
    while r.audio_free() < r.AUDIO_FIFO:     # let the previous level play out first
        time.sleep(0.02)
    word = ((level & 0xFFFF) << 16) | (level & 0xFFFF)
    r.push([word] * 2000)            # 0.65 s of steady audio
    time.sleep(0.35)
    hz = r.rf_hz()
    want = F1 + 0.87 * level / 32767 * 75000
    check('FM: audio %+.1f moves the carrier %+.1f kHz' % (level / 32767, (want - F1) / 1000), near(hz, want, 300),
          '%d Hz (want %d)' % (hz, want))
while r.audio_free() < r.AUDIO_FIFO:
    time.sleep(0.05)

# the power setting and AM, measured as the time the pin is high (the strength is sin(pi x that time)),
# at 6.78 MHz (ISM): long enough periods to measure the width exactly
F2 = 6.78e6
r.frequency(F2)
r.mode('carrier')
r.power(1.0, key=True)
time.sleep(0.25)
bias = r.rf_duty() - 0.5             # the pad switches up and down at slightly different speeds
check('pin edges: rise and fall timing (measured at 50 %)', abs(bias) < 0.03,
      'the pin reads %.1f %% high: %.1f ns of edge difference, taken off the readings below' % (50 + bias * 100, bias / F2 * 1e9))
def duty():
    return r.rf_duty() - bias


def table(strength):
    """The width the FPGA makes for a strength 0..1: its 256-step table (index = strength x 255, rounded down)."""
    i = min(255, int(strength * 32767) >> 7)
    return round(1024 * math.asin(i / 255) / math.pi) / 1024
r.power(0.5, key=True)
time.sleep(0.25)
want = math.asin(0.5) / math.pi
check('power 50 %%: the pin is high %.1f %% of the time' % (want * 100), near(duty(), want, 0.008), '%.1f %%' % (duty() * 100))
r.power(1.0, key=True)
r.am_depth(0.9)
r.mode('am')
for m in (0.5, 0.0, -0.5):
    while r.audio_free() < r.AUDIO_FIFO:
        time.sleep(0.02)
    v = int(m * 32767)
    r.push([((v & 0xFFFF) << 16) | (v & 0xFFFF)] * 2000)
    time.sleep(0.3)
    hz, d = r.rf_hz(), duty()
    want = table(0.5 * (1 + 0.9 * m))
    check('AM 90 %%, sound %+.1f: strength %.2f' % (m, 0.5 * (1 + 0.9 * m)),
          near(d, want, 0.008) and near(hz, F2, 20), 'high %.1f %% (want %.1f %%), %d Hz' % (d * 100, want * 100, hz))
while r.audio_free() < r.AUDIO_FIFO:
    time.sleep(0.02)

# SSB and DSB: the sound becomes I + jQ (a 256-tap complex filter), then strength and phase (CORDIC)
r.setup(tones=True, stereo=False, rds=False, preemph=0)
r.tones(1000, 1000)                  # (L + R) / 2 = a 1 kHz tone at half scale
r.mode('usb')
time.sleep(0.1)
z = r.capture_iq()
n = len(z)
win = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]
def cline(f):
    w = 2 * math.pi * f / FS
    return abs(sum(v * win[i] * cmath.exp(-1j * w * i) for i, v in enumerate(z))) * 2 / n
up, down = cline(1000), cline(-1000)
check('USB: the other side band suppressed', up > 0.4 and down < up / 100,
      '+1 kHz %.3f, -1 kHz %.5f: %.0f dB' % (up, down, 20 * math.log10(up / max(down, 1e-9))))
for name, sign in (('usb', 1), ('lsb', -1)):
    r.mode(name)
    time.sleep(0.3)
    hz, d = r.rf_hz(), duty()
    check('%s: a 1 kHz tone is the carrier %+d Hz, steady strength' % (name.upper(), 1000 * sign),
          near(hz, F2 + 1000 * sign, 20) and near(d, table(abs(up)), 0.008),
          '%+d Hz, high %.1f %% (want %.1f %%)' % (hz - F2, d * 100, 100 * table(abs(up))))
r.mode('dsb')
time.sleep(0.3)
want = sum(table(up * abs(math.cos(2 * math.pi * i / 1000))) for i in range(1000)) / 1000
d, hz = duty(), r.rf_hz()
# where the strength is so small that a pulse is shorter than one 2 ns sample, there is no pulse
seen = sum(1 for i in range(1000) if math.asin(0.5 * abs(math.cos(2 * math.pi * i / 1000))) / math.pi / F2 >= 2e-9) / 1000
check('DSB: the strength follows the sound (no carrier)', near(d, want, 0.008) and near(hz, F2 * seen, F2 * 0.015),
      'high %.1f %% (want %.1f %%), %d Hz (want about %d)' % (d * 100, want * 100, hz, F2 * seen))
# NFM: the voice filter
r.mode('fm')
r.setup(narrow=True)
time.sleep(0.1)
a1 = tone_level(r.capture(), 1000, FS)
r.tones(5000, 5000)
time.sleep(0.1)
a5 = tone_level(r.capture(), 5000, FS)
check('NFM voice filter: 1 kHz passes, 5 kHz is blocked', near(a1, 0.87 * 16383, 0.87 * 16383 * 0.05) and a5 < a1 / 100,
      '1 kHz %.0f, 5 kHz %.1f (%.0f dB)' % (a1, a5, 20 * math.log10(max(a5, 1e-3) / a1)))
r.setup(narrow=False, tones=False)
r.frequency(F1)

# ---------------------------------------------------------------- 4. the symbol player
r.mode('symbols')
g0 = r.symbol_gaps()
r.symbol(+100000, 400000)
r.symbol(-100000, 400000)
r.symbol(0, 400000, width=0)
seen = []
t0 = time.time()
while time.time() - t0 < 1.5:
    seen.append(r.rf_hz())
    time.sleep(0.05)
hi = any(near(v, F1 + 100000, 30) for v in seen)
lo = any(near(v, F1 - 100000, 30) for v in seen)
off = seen[-1] == 0
check('symbols: +100 kHz, -100 kHz, then silent', hi and lo and off,
      ', '.join(sorted({'%.1f' % ((v - F1) / 1000) if v else 'off' for v in seen})) + ' kHz')
check('symbols: one gap counted when the queue ran dry', r.symbol_gaps() == g0 + 1)
# PSK: the phase path. A phase that turns a quarter turn every 1 ms is a carrier 250 Hz higher.
# (Only forward: a sudden step backwards leaves a short extra pulse that the edge counter also counts;
# smooth backward turning is checked by LSB above.)
for sign in (1,):
    r.symbols_flush()
    for i in range(450):
        r.symbol(0, 1000, 512, (sign * 64 * i) & 255)
    time.sleep(0.25)
    hz = r.rf_hz()
    check('PSK phase steps: a turning phase reads %+d Hz' % (250 * sign), near(hz, F1 + 250 * sign, 20),
          '%+d Hz' % (hz - F1))
r.symbols_flush()
for i in range(20):
    r.symbol(+50000, 500000)
time.sleep(0.3)
r.symbols_flush()
time.sleep(0.3)
check('symbols: flush empties the queue and stops the carrier', r.symbols_free() == 512 and r.rf_hz() == 0,
      '%d queued, %d Hz' % (512 - r.symbols_free(), r.rf_hz()))
r.mode('off')
r.setup(tx=False)

# ---------------------------------------------------------------- 5. audio resampler
r.input_rate(24000)
r.push([0] * r.audio_free())
t0 = None
while True:
    n = r.AUDIO_FIFO - r.audio_free()
    if t0 is None and n <= r.AUDIO_FIFO - 200:
        t0, n0 = time.time(), n
    if t0 is not None and n <= 900:
        rate = (n0 - n) / (time.time() - t0)
        break
    time.sleep(0.002)
check('resampler takes 24 kHz audio at 24 kHz', near(rate, 24000, 24000 * 0.03), '%.0f samples/s' % rate)
u0 = r.underruns()
time.sleep(0.2)
check('missing audio is counted (underruns)', r.underruns() > u0)
r.input_rate(3052)
r.push([0x40004000] * 4000)
r.audio_flush()
free = r.audio_free()
r.push([0] * 1000)
time.sleep(0.15)
n = r.AUDIO_FIFO - r.audio_free()
check('audio flush empties the FIFO, playing goes on', free == r.AUDIO_FIFO and 400 < n < 700,
      'free after flush %d, then %d of 1000 left after 0.15 s' % (free, n))
r.audio_flush()
r.input_rate(r.FS_AUDIO)
r.mode('off')
r.setup(tx=False, tones=False, mute=False, stereo=True, rds=True, pilot=True, preemph=50)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
