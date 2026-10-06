# 08 Audio demo: plays a melody made in Python, then a tone sweep from the tone generator; plays
# sound.wav from this project folder if there is one (16-bit PCM, any rate: resampled to 48828 Hz).
import math
import os
import struct
import time
import wave
from blocks import Bus, Audio, require

bus = Bus()
info = require(bus, 'AUD0')
a = Audio(bus, slot=1)
FS = Audio.FS


def notes(seq, bpm=140):
    for name, beats in seq:
        f = 440 * 2 ** ((('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B').index(name[:-1]) - 9) / 12
                        + int(name[-1]) - 4) if name != 'R' else 0
        n = int(FS * 60 / bpm * beats)
        for k in range(n):
            env = min(1, k / 400, (n - k) / 800)
            v = int(12000 * env * math.sin(2 * math.pi * f * k / FS)) if f else 0
            yield v, v


def play_wav(path):
    with wave.open(path) as w:
        ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        if width != 2:
            print('only 16-bit WAV files')
            return
        data = w.readframes(w.getnframes())
    frames = struct.unpack('<%dh' % (len(data) // 2), data)
    step = rate / FS
    n = int(len(frames) / ch / step)
    def gen():
        for i in range(n):
            j = int(i * step) * ch
            yield frames[j], frames[j + 1 if ch == 2 else j]
    print('playing %s (%d Hz, %d channel(s), %.1f s)' % (os.path.basename(path), rate, ch, n / FS), flush=True)
    a.play(gen())


a.setup(out=True, tone=False)
a.volume(0.8)
print('Audio demo: connect a PCM5102A / MAX98357A to J3 (see the guide).')
here = os.path.dirname(os.path.abspath(__file__))
while True:
    info.leds(1)
    if os.path.isfile(os.path.join(here, 'sound.wav')):
        play_wav(os.path.join(here, 'sound.wav'))
    else:
        print('melody', flush=True)
        a.play(notes([('E5', .5), ('D#5', .5), ('E5', .5), ('D#5', .5), ('E5', .5), ('B4', .5), ('D5', .5),
                      ('C5', .5), ('A4', 1.5), ('R', .5), ('C4', .5), ('E4', .5), ('A4', .5), ('B4', 1.5)]))
    info.leds(2)
    print('tone sweep from the tone generator', flush=True)
    a.setup(out=True, tone=True)
    a.volume(0.3)
    for f in range(200, 4000, 50):
        a.tone(f)
        time.sleep(0.03)
    a.setup(out=True, tone=False)
    a.volume(0.8)
    time.sleep(1)
