# 14 FIR filter lab demo: design a low-pass filter, see what it does to a noisy sine, measure its response.
import math
from blocks import Bus, FirLab, fir_design, fir_gain, require

bus = Bus()
require(bus, 'FIR1')
fir = FirLab(bus, slot=1)
fir.reset()

RATE = 100                         # 100 MHz / 100 = 1 million samples per second
FS = 100e6 / RATE
h = fir_design('lowpass', f1=0.05, taps=63)          # cut-off at 5 % of the sample rate: 50 kHz
q = fir.set_filter(h)
print('A 63-tap low-pass filter, cut-off 50 kHz at 1 million samples per second.')
print('Coefficients (18 bit, x 2^-17): %s ...' % ', '.join(str(c) for c in q[28:35]))


def bar(v, width=40):
    n = int(round(max(0.0, min(1.0, v)) * width))
    return '#' * n + '.' * (width - n)


print('\n1. A 10 kHz sine with strong noise, before (x) and after (y) the filter:')
fir.generator(10e3, RATE, amp=12000, noise=12000)
pairs = fir.capture(100)
for x, y in pairs[60:100:2]:
    print('   x %6d |%-21s|   y %6d |%-21s|' % (x, ' ' * int((x + 32768) / 65536 * 20) + '*', y, ' ' * int((y + 32768) / 65536 * 20) + '*'))

print('\n2. The frequency response, measured (the bars) and computed (the numbers):')
freqs = [5e3, 20e3, 40e3, 50e3, 60e3, 80e3, 100e3, 150e3, 200e3, 300e3, 450e3]
gains = fir.response(freqs, RATE)
for f, g in zip(freqs, gains):
    want = fir_gain(q, f / FS) / (1 << fir.SHIFT)
    db = 20 * math.log10(g) if g > 1e-5 else -100
    print('   %6.0f kHz  %s  %6.1f dB  (math: %6.1f dB)' % (f / 1e3, bar(g), db, 20 * math.log10(max(want, 1e-5))))

print('\n3. Live: every second the noise level after the filter (try changing f1, taps or the window)')
fir.generator(10e3, RATE, amp=0, noise=16000)
while True:
    pin, pout = fir.peaks(1.0)
    print('   noise in %5d, out %5d: the filter keeps %4.1f %% of the white noise peaks' % (pin, pout, 100.0 * pout / max(pin, 1)), flush=True)
