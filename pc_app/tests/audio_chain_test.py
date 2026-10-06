"""PC test of fpga_projects/12_fm_radio/audio_chain.py with a stand-in for the FPGA (its sound buffer drains
at 48000 samples per second of simulated time).

    python audio_chain_test.py
"""
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'fpga_projects', '12_fm_radio'))
import audio_chain as ac  # noqa: E402

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail))


class FakeRadio:
    AUDIO_FIFO = 8192

    def __init__(self):
        self.fifo, self.played = [], []

    def audio_free(self):
        return self.AUDIO_FIFO - len(self.fifo)

    def audio_flush(self):
        self.fifo = []

    def input_rate(self, hz):
        pass

    def push(self, words):
        self.fifo += list(words)

    def play(self, n):                     # the FPGA takes n samples
        take, self.fifo = self.fifo[:n], self.fifo[n:]
        self.played += take + [0] * (n - len(take))


def words(l, r):
    l = np.clip(np.round(np.asarray(l) * 32767), -32767, 32767).astype(np.int16).view(np.uint16).astype(np.uint32)
    r = np.clip(np.round(np.asarray(r) * 32767), -32767, 32767).astype(np.int16).view(np.uint16).astype(np.uint32)
    return (l | (r << 16)).tolist()


def unpack(w):
    w = np.asarray(w, dtype=np.uint32)
    return (w & 0xFFFF).astype(np.uint16).view(np.int16) / 32768, (w >> 16).astype(np.uint16).view(np.int16) / 32768


# ---- resampler: a 1 kHz tone at 44100 in chunks of random sizes, at 48000 it must be the same clean tone
random.seed(5)
res = ac.Resampler()
n, out = 0, []
while n < 44100:
    k = random.randint(1, 900)
    t = np.arange(n, n + k) / 44100
    x = np.stack([np.sin(2 * math.pi * 1000 * t), np.cos(2 * math.pi * 1000 * t)], axis=1).astype(np.float32)
    out.append(res.process(x, 44100))
    n += k
y = np.concatenate(out)
t = np.arange(len(y)) / 48000
err = np.abs(y[:, 0] - np.sin(2 * math.pi * 1000 * t)).max()
check('resampler 44.1 -> 48 kHz: length', abs(len(y) - n * 48000 / 44100) <= 2, '%d samples from %d' % (len(y), n))
check('resampler: the tone continues across every chunk', err < 0.02, 'largest error %.4f' % err)

# ---- the processing
ch = ac.Chain()
ch.set(gain_db=12, limiter=True, ceiling_db=-1)
t = np.arange(4800) / 48000
x = np.stack([0.5 * np.sin(2 * math.pi * 440 * t)] * 2, axis=1).astype(np.float32)
y = np.concatenate([ch.process(x[i:i + 480]) for i in range(0, 4800, 480)])
check('limiter: +12 dB on a -6 dB tone stays under -1 dB', np.abs(y).max() <= 10 ** (-1 / 20) + 1e-6,
      'peak %.2f dB' % (20 * math.log10(np.abs(y).max())))
st = ch.stats()
check('meters: in -6 dB, out -1 dB, limiting -7 dB', abs(st['in_peak'][0] + 6) < 0.2 and abs(st['out_peak'][0] + 1) < 0.2
      and abs(st['limiter_db'] + 7) < 0.3, str(st))
ch = ac.Chain()
ch.set(gain_db=6, limiter=False)
y = ch.process(x[:480] * 0.25)
check('gain +6 dB', abs(np.abs(y).max() / np.abs(x[:480] * 0.25).max() - 2.0) < 0.01)
ch.set(mono=True, limiter=False)
z = np.stack([np.ones(480), -np.ones(480) * 0.5], axis=1).astype(np.float32)
check('mono: both sides the average', np.allclose(ch.process(z), 0.25))
ch.set(swap=True, limiter=False)
check('swap L / R', np.allclose(ch.process(z)[:, 0], -0.5))
ch.set(agc=True, agc_target_db=-16, limiter=False)
for i in range(800):                                  # 8 s
    yy = ch.process(np.stack([0.05 * np.sin(2 * math.pi * 440 * np.arange(480) / 48000)] * 2, axis=1).astype(np.float32))
rms = float(np.sqrt((yy ** 2).mean()))
check('AGC brings a quiet sound (-29 dB) up to the target (-16 dB)', abs(20 * math.log10(rms) + 16) < 1.5, 'rms %.1f dB after 8 s' % (20 * math.log10(rms)))

# ---- the delay line: a click goes in at t = 0.2 s, it must come out at 0.2 s + the delay
for delay in (0.0, 1.5):
    fr = FakeRadio()
    sim = [0.0]
    pl = ac.Pipeline(fr, clock=lambda: sim[0])
    pl.chain.set(limiter=False)
    pl.set_delay(delay)
    sent = 0
    for step in range(int(3.0 / 0.005)):              # 5 ms steps of simulated time
        while pl.need() > 0:
            n = 480
            l = np.zeros(n)
            if sent <= 9600 < sent + n:
                l[9600 - sent] = 0.9                  # the click at sample 9600 (0.2 s)
            pl.push(words(l, l))
            sent += n
        pl.pump()
        fr.play(240)
        sim[0] += 0.005
    pl_l, _ = unpack(fr.played)
    at = int(np.argmax(np.abs(pl_l) > 0.5))
    lat = at / 48000 - 0.2
    check('delay %.1f s: the click comes out %.1f s later' % (delay, delay), delay - 0.02 <= lat <= delay + 0.12,
          'it came %.3f s later (the rest is the 0.1 s kept ready)' % lat)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
