# 11 Stream lab self-test: CRC-32 of random frames against zlib, the full-speed stream with and without
# back pressure, and the arbiter keeping frames whole and taking turns.
import os
import random
import time
import zlib
from blocks import Bus, StreamLab, require

results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-50s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)


bus = Bus()
require(bus, 'AXIS')
lab = StreamLab(bus, slot=1)
check('stream lab answers', lab.r(15) == 0x41584953)
lab.reset()
random.seed(11)
bad = 0
for n in (4, 8, 64, 256, 1000):
    data = bytes(random.getrandbits(8) for _ in range(n))
    bad += lab.crc_frame(data) != zlib.crc32(data)
check('CRC-32 of 5 random frames equals zlib.crc32', bad == 0, '%d different' % bad)
check('bytes counted', lab.r(5) == 4 + 8 + 64 + 256 + 1000, '%d' % lab.r(5))

lab.sources(b=True)
lab.slow(0)
time.sleep(2.1)
m = lab.meter()
check('source -> FIFO -> meter at full speed', abs(m['per_sec'] - 100e6) < 2 and m['errors'] == 0,
      '%.2f million words/s, %d errors' % (m['per_sec'] / 1e6, m['errors']))
lab.slow(3)
time.sleep(2.1)
m = lab.meter()
check('with back pressure (1 in 4 clocks)', abs(m['per_sec'] - 25e6) < 2 and m['errors'] == 0,
      '%.2f million words/s, %d errors' % (m['per_sec'] / 1e6, m['errors']))
lab.sources()
lab.slow(0)

lab.reset()
lab.sources(c=True)
time.sleep(0.01)
lab.sources()
words = lab.take(64)
frames, cur, ok = [], [], True
for w, last, src in words:
    cur.append((w, src))
    if last:
        frames.append(cur)
        cur = []
for f in frames:
    srcs = {s for w, s in f}
    tag = 0x10000000 if f[0][1] == 0 else 0x20000000
    seq = [w - tag for w, s in f]
    ok &= len(srcs) == 1 and len(f) == (3 if f[0][1] == 0 else 5) and seq == list(range(seq[0], seq[0] + len(f)))
turns = all(frames[i][0][1] != frames[i + 1][0][1] for i in range(len(frames) - 1))
check('arbiter: %d frames whole, from one source each' % len(frames), ok and len(frames) >= 8)
check('arbiter: the sources take turns', turns)
print('RESULT: %d of %d ok' % (sum(results), len(results)))
