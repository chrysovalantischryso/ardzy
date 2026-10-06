# 11 Stream lab demo: CRC-32 of a text in the FPGA, the speed of a stream, and two sources taking turns.
import time
import zlib
from blocks import Bus, StreamLab, require

bus = Bus()
require(bus, 'AXIS')
lab = StreamLab(bus, slot=1)
lab.reset()

text = b'Ardzy: the Antminer S9 control board used like an Arduino, with an FPGA.   '
text += b' ' * ((-len(text)) % 4)
crc = lab.crc_frame(text)
print('Chain A: CRC-32 of "%s"' % text.decode().strip())
print('   FPGA 0x%08X, Python zlib 0x%08X: %s' % (crc, zlib.crc32(text), 'same' if crc == zlib.crc32(text) else 'DIFFERENT'))

print('Chain B: a counting source into a meter at 100 MHz')
lab.sources(b=True)
for slow in (0, 1, 3, 9):
    lab.slow(slow)
    time.sleep(2.1)
    m = lab.meter()
    print('   meter takes 1 word in %d clocks: %6.2f million words per second, %d sequence errors'
          % (slow + 1, m['per_sec'] / 1e6, m['errors']))
lab.sources()

print('Chain C: two sources (frames of 3 and 5 words) through the arbiter')
lab.reset()
lab.sources(c=True)
time.sleep(0.01)
lab.sources()
words = lab.take(40)
frame = []
for w, last, src in words:
    frame.append(w)
    if last:
        print('   source %d frame: %s' % (src, ' '.join('%08X' % x for x in frame)))
        frame = []
