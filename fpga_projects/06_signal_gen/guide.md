# What it does

A function generator: sine, triangle, sawtooth and square waves from 0.02 Hz up, with amplitude, offset, duty cycle and frequency sweeps. It comes out four ways at the same time: a 1-bit sigma-delta DAC, an 8-bit PWM DAC, a square sync output, and 8 parallel bits for a resistor ladder.

# How it works

**Direct digital synthesis (DDS)**: a 32-bit phase grows by FREQ every clock (100 million times per second). The top 10 bits of the phase pick a value from a 1024-point sine table (or make a triangle, sawtooth or square from the phase itself).

```
frequency = FREQ x 100 MHz / 2^32         (steps of 0.023 Hz)
1 kHz     -> FREQ = 42 950
```

The value is then scaled (AMP), moved (OFFSET), and turned into a voltage:

- **sigma-delta** (J6 pin 5): a 1-bit stream at 100 MHz whose average follows the value. A 1 kohm resistor and a 10 nF capacitor (a low-pass) smooth it into the analog wave: clean up to about 20 kHz.
- **PWM** (J6 pin 11): 8 bits at 390.6 kHz; 1 kohm + 100 nF.
- **sync** (J6 pin 12): high for the first half of each period, a perfect square for a scope trigger or as a clock.
- **R-2R** (J5 + J8, 8 pins): the top 8 bits in parallel: with an R-2R ladder (10 k / 20 k resistors) you get an 8-bit DAC that is good up to several MHz.

A **sweep** adds SWEEP_STEP to FREQ every SWEEP_RATE clocks: the frequency glides from start to stop, for measuring filters and speakers. The FPGA measures the frequency at its own sync pin (read back at the pad) to prove the output.

# Try it

1. A resistor of 1 kohm from J6 pin 5, a 10 nF capacitor from its other end to GND (pin 1): the wave is on the capacitor.
2. A scope on the capacitor and its trigger on J6 pin 12, or headphones through a 10 uF capacitor (keep the volume low).
3. **Upload and run**: the demo steps through the waves, then sweeps 100 Hz to 10 kHz.

# Program it

```python
from blocks import Bus, SignalGen
g = SignalGen(Bus(), slot=1)
g.wave('sine')
g.frequency(440)
g.amplitude(0.8)          # 0..1
g.on()
g.sweep(100, 10000, seconds=5, repeat=True)
print(g.measured_hz())    # counted at the sync pin
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] on [1] sweep running [2] sweep repeats |
| 1 | FREQ | phase step |
| 2 | WAVE | 0 sine, 1 triangle, 2 sawtooth, 3 square |
| 3..5 | AMP, OFFSET, DUTY | 0..65535, signed, 32768 = 50 % |
| 6..8 | SWEEP_STOP, SWEEP_STEP, SWEEP_RATE | the sweep |
| 9 | PHASE | set the phase |
| 10..12 | SAMPLE, MEAS_HZ, FREQ_NOW | (read) |
| 13 | ID | "DDSG" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Direct digital synthesis | a 32-bit phase + FREQ every clock, a 1024-point sine table |
| Digital to analog without a DAC chip | sigma-delta and PWM outputs plus an RC low-pass |
| An R-2R ladder DAC | 8 pins and 8 + 8 resistors make an 8-bit analog output |
| Measuring your own output | the frequency at the sync pin, read back at the pad |

## Exercises

1. What FREQ gives 440 Hz (the note A)?

<details><summary>Answer</summary>
440 x 2^32 / 100 000 000 = 18 898 (18 897.7 rounded): the real frequency is 440.003 Hz.
</details>

2. A 1 kohm and 10 nF low-pass: what is its corner frequency, and why does it suit the sigma-delta output?

<details><summary>Answer</summary>
1 / (2 pi R C) = 15.9 kHz: it keeps audio but removes the 100 MHz switching of the bit stream.
</details>

3. Why is an R-2R ladder good to several MHz while the sigma-delta is clean only to about 20 kHz?

<details><summary>Answer</summary>
The ladder outputs the whole 8-bit value at once every clock; the sigma-delta needs many clocks of 1-bit pulses averaged by a slow filter to make one value.
</details>

# Ideas

- A two-tone (DTMF) generator: two blocks added together.
- A frequency response meter: sweep through a filter and measure the level with the Zynq's XADC.
- A clock source for another circuit: sync output up to 25 MHz.

# If something is wrong

- **The wave is stairs or fuzzy**: the RC filter is missing or too small; the sigma-delta needs 10 nF with 1 kohm.
- **The level is low**: the outputs swing 0 to 3.3 V; the RC filter adds no gain. Use an op-amp for more.
