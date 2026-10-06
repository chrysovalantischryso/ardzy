# What it does

A **digital filter** in hardware, the kind inside every phone, sound card, radio and hearing aid: it keeps some frequencies and removes others. You design the filter in Python (low-pass, high-pass, band-pass, band-stop), the FPGA runs it on up to 1.5 million samples per second, and the results equal the math to the last bit.

- Up to **64 taps** (coefficients), 18-bit coefficients, 16-bit samples, a 48-bit accumulator.
- Samples from the **ARM** (your data, sound) or from a built-in **generator** (a sine of any frequency plus white noise).
- **Peak meters** on the input and the output: sweep the generator and you have measured the filter's frequency response.

Nothing to connect. LED 0 shows how busy the filter is.

# How it works

## 1. What a FIR filter computes

A FIR (finite impulse response) filter makes each output sample from the last N input samples, each multiplied by its own coefficient:

```
y[n] = c[0] x[n] + c[1] x[n-1] + c[2] x[n-2] + ... + c[N-1] x[n-N+1]
```

That is all. The coefficients decide what the filter does. A moving average (all c = 1/N) is the simplest low-pass: fast wiggles average out, slow changes stay.

<figure>
<svg viewBox="0 0 860 210" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="FIR filter structure">
<defs><marker id="ah14" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<text x="10" y="45" class="d-text">x[n]</text>
<path d="M50 40 H86" class="d-arrow" marker-end="url(#ah14)" color="#b8860b"/>
<rect x="90" y="22" width="70" height="36" rx="6" class="d-box"/><text x="125" y="45" class="d-small" text-anchor="middle">delay</text>
<path d="M160 40 H196" class="d-arrow" marker-end="url(#ah14)" color="#b8860b"/>
<rect x="200" y="22" width="70" height="36" rx="6" class="d-box"/><text x="235" y="45" class="d-small" text-anchor="middle">delay</text>
<path d="M270 40 H306" class="d-arrow" marker-end="url(#ah14)" color="#b8860b"/>
<text x="320" y="45" class="d-text">. . .</text>
<path d="M70 40 V96" class="d-line" marker-end="url(#ah14)" color="#888"/><path d="M180 40 V96" class="d-line" marker-end="url(#ah14)" color="#888"/><path d="M290 40 V96" class="d-line" marker-end="url(#ah14)" color="#888"/>
<circle cx="70" cy="115" r="17" class="d-pl"/><text x="70" y="120" class="d-text" text-anchor="middle">x</text><text x="96" y="120" class="d-small">c0</text>
<circle cx="180" cy="115" r="17" class="d-pl"/><text x="180" y="120" class="d-text" text-anchor="middle">x</text><text x="206" y="120" class="d-small">c1</text>
<circle cx="290" cy="115" r="17" class="d-pl"/><text x="290" y="120" class="d-text" text-anchor="middle">x</text><text x="316" y="120" class="d-small">c2</text>
<path d="M70 132 V170 H560" class="d-line"/><path d="M180 132 V170" class="d-line"/><path d="M290 132 V170" class="d-line"/>
<rect x="560" y="150" width="90" height="40" rx="6" class="d-acc"/><text x="605" y="175" class="d-title" text-anchor="middle">sum</text>
<path d="M650 170 H716" class="d-arrow" marker-end="url(#ah14)" color="#b8860b"/><text x="725" y="175" class="d-text">y[n]</text>
<text x="430" y="115" class="d-small">N multiplications and N additions</text><text x="430" y="133" class="d-small">for every sample</text>
</svg>
<figcaption>The textbook picture: a line of delays, one multiplier per tap, one big sum.</figcaption>
</figure>

## 2. How the FPGA does it with one multiplier

Drawing it as the textbook does needs 64 multipliers; the chip has 80, so it would fit, but most of them would wait. Here **one** multiplier (a DSP48 slice, made for exactly this) does one tap per clock, again and again:

1. A new sample goes into a 64-word memory (the history) at the next place.
2. For k = 0 .. N-1 the design reads x[n-k] and c[k] (stage 1), multiplies them (stage 2) and adds the product to the accumulator (stage 3). The three stages work on three different taps at the same time: a **pipeline**.
3. After the last tap the accumulator holds the sum. It is shifted right by SHIFT bits (dividing by 2^SHIFT), limited to 16 bits and sent to the output FIFO.

A sample takes N + 4 clocks: 68 clocks for 64 taps, 1.47 million samples per second.

The end of the chain is a pipeline too: dividing the 48-bit sum by 2^SHIFT (a "barrel shifter", 6 levels of multiplexers), limiting it to 16 bits and updating the meters took 13 ns in the first version, longer than one 10 ns clock. Now each of the three gets its own clock; a result leaves 3 clocks later, and a new sample can start meanwhile.

> **info** Time-sharing one multiplier is the classic DSP trade-off: fewer multipliers = less chip, more clocks per sample. A 4-tap filter could do 12 million samples per second with the same hardware.

## 3. Numbers without a decimal point (fixed point)

The FPGA has no floating point here: everything is integers. A coefficient like 0.0732 becomes `round(0.0732 x 2^17) = 9594`, and the result is divided by 2^17 again at the end (SHIFT = 17). 18-bit coefficients give about 5 decimal digits of precision, enough for filters that remove 60 to 80 dB. The accumulator has 48 bits, so even 64 full-scale products cannot overflow it.

## 4. Designing a filter

`fir_design()` in `blocks.py` uses the **windowed sinc** method: the ideal low-pass filter's coefficients are a sinc function (sin x / x); cutting it to N taps makes ripples, and a window (Hamming, Blackman) smooths the cut. More taps = a steeper edge between pass and stop.

| Filter | Keeps | Example |
|---|---|---|
| low-pass, f1 | below f1 | remove hiss above the voice |
| high-pass, f1 | above f1 | remove hum and rumble |
| band-pass, f1 .. f2 | f1 to f2 | pick one radio channel or tone |
| band-stop, f1 .. f2 | all but f1 to f2 | remove 50 Hz mains hum |

Frequencies are given as a fraction of the sample rate (0 to 0.5, because a sampled signal cannot hold anything above half its sample rate: the Nyquist limit).

# Try it

Nothing to wire. **Upload and run**. The Monitor shows:

1. A 10 kHz sine buried in noise before and after a 50 kHz low-pass filter: the noise is gone, the sine stays.
2. The frequency response measured with the generator next to the computed one: they agree.
3. Live noise levels: change `f1`, `taps` or the window in `main.py` and upload again.

# Program it

```python
from blocks import Bus, FirLab, fir_design, fir_gain
fir = FirLab(Bus(), slot=1)
fir.reset()
q = fir.set_filter(fir_design('bandpass', f1=0.1, f2=0.15, taps=63))
print(fir.filter([0, 1000, 0, -1000] * 50))          # your own samples through the filter
fir.generator(120e3, rate=100, amp=16000)            # a 120 kHz sine at 1 million samples/s
print(fir.peaks(0.1))                                 # (largest |input|, largest |output|)
print(fir.response([50e3, 120e3, 200e3]))             # measured gains
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] reset [1] source: 0 ARM, 1 generator |
| 1 | STATUS | [7:0] input FIFO, [17:8] output FIFO, [24] busy |
| 2, 3 | TAPS, SHIFT | 1 .. 64 taps; the result is divided by 2^SHIFT |
| 4, 5 | IN, OUT | write a sample; read [31:16] the result and [15:0] its input |
| 7 .. 10 | GEN_FREQ, GEN_RATE, GEN_AMP, GEN_NOISE | the generator |
| 11, 12 | PEAK_IN, PEAK_OUT | the meters (start over when read) |
| 13, 14, 16 | SAMPLES, CLIPPED, LOST | counters |
| 15 | CAPTURE | the generator's next n results also go to the FIFO |
| 64 .. 127 | COEF | signed 18-bit coefficients |
| 1023 | ID | "FIR1" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Multiply-accumulate (MAC), the heart of all DSP | `fir_lab.v`: `prod <= xa * ca`, `acc <= acc + prod` |
| A pipeline: issue, multiply, accumulate on different taps at once | the `v1`, `v2` valid flags |
| Fixed-point arithmetic | `set_filter()` scales by 2^17, SHIFT divides back |
| Hardware equal to a model, bit for bit | `selftest.py`: 900 random samples against Python |
| FIFOs between fast hardware and slow software | `ardzy_axis_fifo` on the input and the output |

## Exercises

1. **Moving average.** Make an 8-tap moving average: `fir.set_coef([1 << 14] * 8, 17)` (each coefficient is 1/8). Feed it `[0]*8 + [8000]*16 + [0]*16` with `fir.filter()` and print the result. Why does it climb in 8 steps?

<details><summary>Answer</summary>
Each output is the average of the last 8 inputs; when the step arrives, one more of the 8 is 8000 at each sample: 1000, 2000, ... 8000. It falls the same way after the step ends.
</details>

2. **Find the cut-off.** With the demo's 63-tap low-pass (f1 = 0.05 at 1 MS/s), use `fir.response()` to find the frequency where the gain is 0.5 (-6 dB). Why is it at about 50 kHz?

3. **Taps against steepness.** Design the same low-pass with 15, 31 and 63 taps. Measure the gain at 80 kHz for each. What does doubling the taps do?

<details><summary>Answer</summary>
The transition from pass to stop gets about twice as narrow with twice the taps, so at 80 kHz the 63-tap filter removes much more (tens of dB) than the 15-tap one.
</details>

4. **Remove a hum.** Make a band-stop at 50 kHz +- 5 kHz (`fir_design('bandstop', 0.045, 0.055, 63)`) and run the generator at 50 kHz and at 20 kHz. Compare the output peaks.

5. **How many multipliers?** The chip has 80 DSP48 slices. If you used all of them for one filter (one tap each), how many samples per second could a 64-tap filter process?

<details><summary>Answer</summary>
With one multiplier per tap a sample per clock is possible: 100 million samples per second, 68 times more than now. That is how FPGAs filter radio signals in real time.
</details>

# Ideas

- Filter real sound: record with project 08 (I2S microphone), filter here, play back.
- An equalizer: three band-pass filters (bass, middle, treble) with adjustable gains.
- A decimating filter: keep only every 10th result, for a sample rate converter.
- Use it as the channel filter of an SDR receiver (with an ADC on the pins).

# If something is wrong

- **Results are all 32767 or -32768 (CLIPPED grows)**: the coefficients are too large for SHIFT; use `set_filter()` (it scales correctly) or a larger SHIFT.
- **LOST grows**: the output FIFO (512 results) was full; read results more often or use CAPTURE with a smaller n.
- **The response at high frequencies looks a little low**: the peak meter sees the sampled points of a fast sine, not always its very top. Measure longer or lower the frequency.
