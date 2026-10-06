"""audio_chain.py - the sound path of the Ardzy radio on the ARM, before the FPGA (numpy).

    source (songs, pictures, network / PC sound, any rate)
      -> resampler (to 48000 samples per second: every source the same, songs follow each other without gaps)
      -> processing: swap L / R, mono, gain, balance, AGC (a slow level control), limiter (never above the ceiling)
      -> delay line (0 .. 10 s)
      -> the FPGA's sound buffer (8192 places) -> pre-emphasis, 15 kHz filter, stereo, MPX, FM ...
The meters measure the sound coming in (before the processing) and going out (after it), the waveforms
and the level history are kept for the radio's page. The FPGA's test tones do not pass here.
"""
import array
import collections
import math
import time

import numpy as np

RATE = 48000


def db(x):
    return round(20 * math.log10(x), 1) if x > 1e-5 else -100.0


class Resampler:
    """Linear interpolation from any rate to 48000, keeping the position between chunks."""

    def __init__(self):
        self.rate, self.pos, self.last = None, 0.0, None

    def process(self, x, rate):
        """x: float32 array (n, 2) at `rate` -> (m, 2) at RATE."""
        if rate == RATE:
            return x
        if rate != self.rate:
            self.rate, self.pos, self.last = rate, 0.0, None
        if self.last is not None:
            x = np.concatenate((self.last[None, :], x))
            start = self.pos
        else:
            start = 0.0
        step = rate / RATE
        n = len(x)
        t = np.arange(start, n - 1, step)
        if len(t) == 0:
            self.last, self.pos = x[-1], start - (n - 1)
            return np.zeros((0, 2), np.float32)
        i = t.astype(np.int64)
        f = (t - i)[:, None].astype(np.float32)
        y = x[i] * (1 - f) + x[i + 1] * f
        self.pos = t[-1] + step - (n - 1)                # where the next sample falls, from the last one kept
        self.last = x[-1]
        return y


class Chain:
    """The processing, with its meters."""

    def __init__(self):
        self.set()
        self.agc_gain, self.lim_gain = 1.0, 1.0
        self.reset_meters()
        self.history = collections.deque(maxlen=300)    # (time, in peak, out peak) every 0.1 s
        self.h_in = self.h_out = 0.0
        self.h_t = time.time()
        self.scope_in = self.scope_out = np.zeros((0, 2), np.float32)
        self.tail_in = self.tail_out = np.zeros((0, 2), np.float32)   # the last 4096 samples, for the analyzer

    def set(self, gain_db=0.0, balance=0.0, mono=False, swap=False, agc=False, agc_target_db=-16.0,
            limiter=True, ceiling_db=-1.0, bypass=False):
        self.gain = 10 ** (float(gain_db) / 20)
        self.balance = max(-1.0, min(1.0, float(balance)))
        self.mono, self.swap, self.agc, self.limiter, self.bypass = bool(mono), bool(swap), bool(agc), bool(limiter), bool(bypass)
        self.agc_target = 10 ** (float(agc_target_db) / 20)
        self.ceiling = 10 ** (min(0.0, float(ceiling_db)) / 20)

    def reset_meters(self):
        self.m = {'in_peak': [0.0, 0.0], 'in_sq': [0.0, 0.0], 'out_peak': [0.0, 0.0], 'out_sq': [0.0, 0.0], 'n': 0, 'gr': 1.0}

    def _measure(self, x, key):
        """Peaks and energy of both channels; returns the larger peak."""
        p = np.maximum(x.max(axis=0), -x.min(axis=0))
        sq = np.einsum('ij,ij->j', x, x)
        pk, s = self.m[key + '_peak'], self.m[key + '_sq']
        pk[0], pk[1] = max(pk[0], float(p[0])), max(pk[1], float(p[1]))
        s[0] += float(sq[0])
        s[1] += float(sq[1])
        return max(float(p[0]), float(p[1]))

    @staticmethod
    def _ramp(g0, g1, n):
        return np.linspace(g0, g1, n, endpoint=False, dtype=np.float32)[:, None] if n else None

    def process(self, x):
        """x: float32 (n, 2), -1 .. 1 -> the same after the processing."""
        n = len(x)
        if not n:
            return x
        p_in = self._measure(x, 'in')
        self.m['n'] += n
        y = x
        if not self.bypass:
            if self.swap:
                y = y[:, ::-1]
            if self.mono:
                y = np.repeat(y.mean(axis=1, keepdims=True), 2, axis=1)
            gl, gr = self.gain * min(1.0, 1 - self.balance), self.gain * min(1.0, 1 + self.balance)
            if gl != 1.0 or gr != 1.0:
                y = y * np.array([gl, gr], np.float32)
            if self.agc:
                rms = float(np.sqrt(np.einsum('ij,ij->', y, y) / (2 * n)))
                if rms > 0.003:                                  # (below -50 dB it holds: no pumping up the noise)
                    want = max(0.25, min(8.0, self.agc_target / rms))
                    k = min(1.0, n / RATE / (0.3 if want < self.agc_gain else 3.0))   # down fast, up slowly
                    g1 = self.agc_gain + (want - self.agc_gain) * k
                else:
                    g1 = self.agc_gain
                if g1 != self.agc_gain or g1 != 1.0:
                    y = y * self._ramp(self.agc_gain, g1, n) if g1 != self.agc_gain else y * np.float32(g1)
                self.agc_gain = g1
            if self.limiter:
                p = float(max(y.max(), -y.min()))
                want = min(1.0, self.ceiling / p) if p > 0 else 1.0
                g0 = self.lim_gain
                g1 = want if want < g0 else min(want, g0 + n / RATE / 0.5)   # release in 0.5 s
                if g1 != g0:
                    y = y * self._ramp(g0, g1, n)
                elif g1 != 1.0:
                    y = y * np.float32(g1)
                self.lim_gain = g1
                if p * max(g0, g1) > self.ceiling:
                    y = np.clip(y, -self.ceiling, self.ceiling)   # (a fast peak inside the chunk)
                self.m['gr'] = min(self.m['gr'], self.lim_gain)
        if y is x or float(max(y.max(), -y.min())) > 1.0:
            y = np.clip(y, -1.0, 1.0)
        p_out = self._measure(y, 'out')
        # waveforms (the last 20 ms) and the level history
        self.scope_in = x[-960:]
        self.scope_out = y[-960:]
        self.tail_in = np.concatenate((self.tail_in, x))[-TAIL:]
        self.tail_out = np.concatenate((self.tail_out, y))[-TAIL:]
        self.h_in = max(self.h_in, p_in)
        self.h_out = max(self.h_out, p_out)
        now = time.time()
        if now - self.h_t >= 0.1:
            self.history.append((round(now, 2), db(self.h_in), db(self.h_out)))
            self.h_in = self.h_out = 0.0
            self.h_t = now
        return y

    def stats(self):
        """The meters since the last call, in dB (and then they start over)."""
        m, n = self.m, max(1, self.m['n'])
        out = {'in_peak': [db(v) for v in m['in_peak']], 'in_rms': [db(math.sqrt(v / n)) for v in m['in_sq']],
               'out_peak': [db(v) for v in m['out_peak']], 'out_rms': [db(math.sqrt(v / n)) for v in m['out_sq']],
               'limiter_db': db(m['gr']) if self.limiter and not self.bypass else 0.0,
               'agc_db': db(self.agc_gain) if self.agc and not self.bypass else 0.0, 'samples': m['n']}
        self.reset_meters()
        return out

    def scope(self, points=160):
        def pick(a):
            if not len(a):
                return []
            i = np.linspace(0, len(a) - 1, points).astype(int)
            return [[int(round(v * 100)) for v in a[i, 0]], [int(round(v * 100)) for v in a[i, 1]]]
        return {'in': pick(self.scope_in), 'out': pick(self.scope_out)}


    def rta(self):
        """A real-time analyzer: the level in 31 third-octave bands (20 Hz .. 20 kHz) of the sound coming in and
        going out (the last 85 ms, both channels together), and how alike left and right are going out
        (+1 the same = mono, 0 unrelated, -1 opposite: it would cancel on a mono radio)."""
        out = {'bands': RTA_HZ}
        for key, a in (('in', self.tail_in), ('out', self.tail_out)):
            if len(a) < TAIL:
                out[key] = None
                continue
            s = np.abs(np.fft.rfft(a * RTA_WIN, axis=0)) ** 2
            p = s.sum(axis=1)
            e = np.add.reduceat(p, RTA_EDGES)[:len(RTA_HZ)]
            out[key] = [round(10 * math.log10(v * RTA_K + 1e-12), 1) for v in e]
        a = self.tail_out
        if len(a):
            ll, rr, lr = float(np.dot(a[:, 0], a[:, 0])), float(np.dot(a[:, 1], a[:, 1])), float(np.dot(a[:, 0], a[:, 1]))
            out['corr'] = round(lr / math.sqrt(ll * rr), 2) if ll > 1e-6 and rr > 1e-6 else None
        return out


TAIL = 4096
RTA_HZ = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000,
          2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000]
RTA_WIN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(TAIL) / TAIL)).astype(np.float32)[:, None]
# band edges (FFT bins) at the geometric middle between the band centres; the lowest bands share bins
RTA_EDGES = np.array([max(1, int(round(f * 2 ** (-1 / 6) * TAIL / RATE))) for f in RTA_HZ] + [TAIL // 2], np.intp)
RTA_EDGES = np.maximum.accumulate(RTA_EDGES)
RTA_K = 2.0 / (float((RTA_WIN ** 2).sum()) * TAIL / 2)   # a full-scale sine (both channels) reads about 0 dB


class Pipeline:
    """Sources -> resampler -> processing -> delay line -> the FPGA's sound buffer."""
    AHEAD = 4800                                         # samples kept ready beyond the delay (0.1 s)

    def __init__(self, radio, clock=time.time):
        self.r = radio
        self.clock = clock                               # (a test gives its own)
        self.res = Resampler()
        self.chain = Chain()
        self.buf = collections.deque()
        self.total = 0
        self.delay_s = 0.0
        self.start_margin = 0                            # a live source: also its buffer must be there before playing
        self.reset()

    def reset(self):
        """Empty everything (a new source)."""
        self.buf.clear()
        self.total = 0
        self.playing = False                             # sound has come out of the delay line
        self.start_margin = 0
        self.t_push = None                               # when sound last came in
        self.t0 = None                                   # when the first sound went in
        self.res = Resampler()
        self.r.audio_flush()
        self.r.input_rate(RATE)

    def set_delay(self, s):
        s = max(0.0, min(10.0, float(s)))
        drop = int((self.delay_s - s) * RATE)            # shorter: the samples that are now late go
        if s > self.delay_s and self.playing:            # longer: wait (in real time) until it is filled
            self.playing = False
            self.t0 = self.clock() - self.total / RATE
        self.delay_s = s
        while drop > 0 and self.buf:
            a = self.buf[0]
            if len(a) <= drop:
                self.buf.popleft()
                self.total -= len(a)
                drop -= len(a)
            else:
                self.buf[0] = a[drop:]
                self.total -= drop
                drop = 0

    def hold(self):
        """Samples held back for the delay. When nothing new comes in (the stream stopped, the last song
        ended), what is left plays out in real time: the hold shrinks as the time goes by."""
        h = int(self.delay_s * RATE)
        if h and self.t_push is not None:
            idle = self.clock() - self.t_push - 0.1
            if idle > 0:
                h = max(0, h - int(idle * RATE))
        return h

    def level(self):
        """Samples ready to play beyond the delay (the FPGA's buffer included)."""
        return self.r.AUDIO_FIFO - self.r.audio_free() + max(0, self.total - self.hold())

    def need(self):
        """How many samples a source that can go faster than real time (a song, a picture) may add now.
        Until the delay is filled it goes at real-time pace (else the delay line would fill at once and
        there would be no delay); after that the sound coming out sets the pace."""
        if self.delay_s <= 0 or self.playing:
            return self.AHEAD - self.level()
        if self.t0 is None:
            return self.AHEAD
        return int((self.clock() - self.t0) * RATE) + 1 - self.total     # (exactly real time while it fills)

    def ready(self):
        """Sound is coming out (the delay and the buffer are filled)."""
        return self.playing

    def push(self, words, rate=RATE):
        """FIFO words (right << 16 | left) at `rate`."""
        w = np.frombuffer(words, dtype=np.uint32) if isinstance(words, (array.array, bytes)) else np.asarray(words, dtype=np.uint32)
        if not len(w):
            return
        x = w.view(np.int16).reshape(-1, 2).astype(np.float32)      # (little endian: left, right)
        x *= np.float32(1 / 32768)
        x = self.res.process(x, rate)
        y = self.chain.process(x)
        out = np.ascontiguousarray((y * np.float32(32767)).astype(np.int16)).view(np.uint32).reshape(-1)
        self.buf.append(out)
        self.total += len(out)
        self.t_push = self.clock()
        if self.t0 is None:
            self.t0 = self.t_push

    def pump(self):
        """Move what is due (older than the delay) into the FPGA."""
        free = self.r.audio_free()
        if not self.playing and self.total - self.hold() < self.start_margin and self.clock() - (self.t_push or 0) < 0.3:
            return                                       # (the delay and the buffer fill first)
        n = min(free, self.total - self.hold())
        if n > 0:
            self.playing = True
        while n > 0 and self.buf:
            a = self.buf[0]
            if len(a) <= n:
                self.buf.popleft()
            else:
                self.buf[0] = a[n:]
                a = a[:n]
            self.total -= len(a)
            n -= len(a)
            self.r.push(a.tolist())

    def delay_now(self):
        """The delay the sound has now: what waits in the delay line and in the FPGA."""
        return round((self.total + self.r.AUDIO_FIFO - self.r.audio_free()) / RATE, 2)
