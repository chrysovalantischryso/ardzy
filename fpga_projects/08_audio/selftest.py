# 08 Audio self-test: needs nothing connected. Checks the clocks at the pins, plays samples and receives
# them back through the DOUT pin itself (read back at the pad), the tone generator, and the PDM path with
# a modulated test tone through the CIC filter.
import math
import random
import time
from blocks import Bus, Audio, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


def freq_of(xs, fs):
    """frequency from the zero crossings"""
    z = [i for i in range(1, len(xs)) if xs[i - 1] < 0 <= xs[i]]
    return (len(z) - 1) * fs / (z[-1] - z[0]) if len(z) > 2 else 0


bus = Bus()
require(bus, 'AUD0')
a = Audio(bus, slot=1)
check('audio block answers', a.r(11) == 0x41554430)
a.setup(out=True)
time.sleep(0.05)
check('LRCLK 48828 Hz at the pin', abs(a.lrclk_hz() - 48828.125) < 1, '%.1f Hz' % a.lrclk_hz())

# samples out, back in through the DOUT pin: preload 900 samples with the sound off, then switch the
# sound and the input on with one register write, so all of them come back into the 1024-sample in buffer
a.volume(1.0)
random.seed(9)
sent = [(random.randint(-30000, 30000), random.randint(-30000, 30000)) for _ in range(900)]
a.preload(sent)
a.drain()
a.w(8, 0)                                  # clear the overflow count
a.setup(out=True, rx=True, rx_source='pin')
time.sleep(0.03)                           # 900 samples last 18.4 ms
got = a.record(1000, timeout=1)
a.setup(out=False)
start = next((i for i in range(len(got) - 899) if got[i] == sent[0] and got[i + 1] == sent[1]), None)
ok = start is not None and got[start:start + 900] == sent
check('900 stereo samples out and back through the DOUT pin', ok,
      'found at %s, %d of 900 matching' % (start, sum(1 for x, y in zip(got[start or 0:], sent) if x == y)))

# tone generator, received through the inside loop
a.setup(out=True, tone=True, rx=True, rx_source='loop')
a.tone(1000)
a.volume(0.5)
time.sleep(0.02)
a.drain()
rec = a.record(4800)
left = [l for l, r in rec]
f = freq_of(left, Audio.FS)
peak = max(abs(x) for x in left)
check('tone generator 1000 Hz', abs(f - 1000) < 2, '%.1f Hz, peak %d (half volume: about 16384)' % (f, peak))

# PDM: a modulated test tone through the CIC filter
a.setup(out=True, rx=True, rx_source='pdm', pdm_test=True, tone=True)
a.tone(440)
a.volume(1.0)
time.sleep(0.05)
a.drain()
rec = a.record(4800)
mono = [l for l, r in rec[200:]]
f = freq_of(mono, Audio.FS)
check('PDM path (CIC filter) gives the 440 Hz tone back', abs(f - 440) < 2 and max(mono) > 8000,
      '%.1f Hz, peak %d' % (f, max(mono)))
a.setup(out=False)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
