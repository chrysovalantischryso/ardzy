# What it does

Digital sound in and out: I2S to a DAC or amplifier module (headphones, a speaker), I2S in from an ADC module, and a PDM microphone with the decimation filter in hardware. 48.8 kHz, 16-bit stereo. The demo plays a melody made in Python, a tone sweep, and `sound.wav` if you put one in the project.

# How it works

**I2S** is how chips pass sound: **BCLK** (bit clock), **LRCLK** (which channel: left or right, it is also the sample rate) and **DATA** (the bits, most significant first). Here one 100 MHz clock makes everything:

| Signal | Rate |
|---|---|
| MCLK (for modules that need it) | 12.5 MHz |
| BCLK | 3.125 MHz (64 bits per frame) |
| LRCLK = sample rate | 48828.125 Hz (100 MHz / 2048) |

That is not 48 kHz exactly, but DACs with their own PLL (PCM5102A, MAX98357A, UDA1334A) take any rate. Python resamples your sound to 48828 Hz.

The ARM writes samples into a 2048-sample FIFO (42 ms); the FPGA sends one frame per LRCLK period. If the FIFO runs empty, the FPGA counts an underflow and sends silence. The **tone generator** (a DDS with a sine table) plays without the ARM.

A **PDM microphone** sends 1-bit samples at 3.125 MHz: the density of ones is the sound. A CIC filter (sums and differences) in the FPGA turns them into 16-bit samples at 48.8 kHz.

The DOUT pin is read back at its pad and received again: the self-test plays samples and checks they come back exactly.

# Try it

| Module | Wiring |
|---|---|
| PCM5102A DAC | BCK to J3 pin 11, DIN to J3 pin 12, LCK to J3 pin 15, SCK to GND, VIN 3.3 V, GND |
| MAX98357A amplifier | BCLK J3 pin 11, DIN J3 pin 12, LRC J3 pin 15, VIN 3.3 or 5 V, GND, a 4 to 8 ohm speaker |
| PDM microphone | CLK J6 pin 11, DATA J6 pin 12, SEL to GND, 3.3 V, GND |
| I2S ADC | its DOUT to J6 pin 5, its clocks from J3 |

**Upload and run**. Put a WAV file named `sound.wav` (16-bit PCM) in the project to hear it.

# Program it

```python
from blocks import Bus, Audio
import math
a = Audio(Bus(), slot=1)
a.setup(out=True)
a.volume(0.5)
fs = a.FS
a.play((int(8000 * math.sin(2 * math.pi * 440 * n / fs)),) * 2 for n in range(int(fs)))   # 1 s of A4
a.setup(out=True, tone=True)
a.tone(1000)                         # the hardware tone generator
a.setup(out=False, rx=True, rx_source='pdm')
samples = a.record(48828)            # 1 s from the microphone
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] out on [1] tone [3:2] in source: DIN, loop, DOUT pin, PDM [4] in on [5] PDM test |
| 1, 2 | TX, TX_LEVEL | put a sample (R x 65536 + L) / samples waiting |
| 3, 4 | RX, RX_LEVEL | take a received sample / waiting |
| 5, 6 | TONE_INC, VOLUME | tone frequency, volume 0..256 |
| 7, 8 | UNDERFLOWS, OVERFLOWS | gaps / lost samples |
| 9, 10 | LR_PERIOD, FS | measured at the pin; 48828 |
| 11 | ID | "AUD0" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Deriving clocks by division | MCLK, BCLK and LRCLK all from 100 MHz |
| A FIFO absorbs the software's irregular timing | 2048 samples = 42 ms in hand |
| Serial audio (I2S) | DATA most significant bit first, LRCLK selects the channel |
| Turning 1-bit PDM into samples | a CIC filter: sums and differences |

## Exercises

1. Why can the board's I2S run at 48 828 Hz instead of 48 000 Hz?

<details><summary>Answer</summary>
100 MHz / 2048 = 48 828.125 Hz is a whole divider of the clock; DACs with their own PLL lock to whatever LRCLK they get. Python resamples the sound to match.
</details>

2. The FIFO holds 2048 samples. How long may Python pause before the sound breaks?

<details><summary>Answer</summary>
2048 / 48 828 = 42 ms: any pause shorter than that (minus what is still in the FIFO) is heard as nothing.
</details>

3. A PDM microphone sends 3.125 million bits per second. Why does a filter turn them into sound?

<details><summary>Answer</summary>
The density of ones follows the air pressure. A low-pass filter averages the bits: the average is the sound sample; decimating by 64 gives 48.8 kHz.
</details>

# Ideas

- An internet radio player (the board has a network), a doorbell, sound effects for a game.
- A spectrum analyzer on the VGA screen from the microphone.
- Feed the FM radio (project 12) from the microphone: a live studio.

# If something is wrong

- **Silence with a PCM5102A**: its SCK pin must go to GND (it then makes its own clock), FMT and XSMT as the module's instructions say (XSMT high = not muted).
- **Crackling**: the FIFO runs empty: write in bigger bursts (`play()` does that), and close other programs.
