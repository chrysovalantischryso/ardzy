# What it does

Counts rotary encoders (the knobs with clicks, KY-040) and motor encoders: two channels on J5, position and speed, never missing a step, even at millions of counts per second. The demo shows both positions and speeds and puts encoder 0 on the 4 LEDs.

# How it works

An encoder has two outputs, **A** and **B**, square waves a quarter period apart. The order of their edges gives the direction: A rises before B one way, B before A the other way. Every edge of A or B is one count, so an encoder with 20 lines gives 80 counts per turn.

```
     ___     ___
A __|   |___|   |___      one direction: A leads B
       ___     ___
B ____|   |___|   |___
```

Software on Linux would miss edges when the knob turns fast; the FPGA looks at both pins every 10 ns. A **glitch filter** takes a level only after it was steady for 0.2 us (bouncing contacts of cheap knobs make short spikes). If A and B change in the same clock, the step is impossible to tell: that is counted in ERRORS (too fast, or noise).

The speed is the number of counts in a gate time (0.1 s by default).

For the self-test there is a **generator** inside: it makes A/B signals at a set speed, either straight into the counters or out on encoder 0's real pins, so the whole path through the pads is checked.

# Try it

1. A KY-040 board: **CLK** to J5 pin 5 (A), **DT** to J5 pin 11 (B), **+** to 3.3 V (pin 16), **GND** to pin 1. The second encoder: J5 pins 12 and 15.
2. Bare knobs without a board need pull-ups: the FPGA pins have them, and the common pin goes to GND.
3. **Upload and run**, turn the knob.

# Program it

```python
from blocks import Bus, Encoders
enc = Encoders(Bus(), slot=1)
enc.config(0, reverse=False, filter_ns=500)   # longer filter for cheap knobs
enc.count(0, 0)                                # set position 0
while True:
    print(enc.count(0), enc.speed(0), 'counts per gate', enc.errors(0))
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 8c + 0 | COUNT | position of channel c (signed), write sets it |
| 8c + 1 | SPEED | counts in the last gate |
| 8c + 2 | ERRORS | impossible steps |
| 8c + 3 | CFG | [0] reverse, [15:8] filter clocks |
| 64 | GATE | speed gate in clocks |
| 65..68 | TEST, GEN_PERIOD, GEN_RUN, GEN_DONE | the test generator |
| 69 | ID | "QUAD" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Quadrature decoding: direction from edge order | A leads B one way, B leads A the other |
| Glitch filtering | a level is taken only after 0.2 us without change |
| Counting in hardware never misses | every edge seen at 100 MHz |
| A test generator inside the design | A/B signals made by the FPGA to test its own counters |

## Exercises

1. An encoder with 24 lines turns once per second. How many counts per second?

<details><summary>Answer</summary>
Every edge of A and B counts: 4 x 24 = 96 counts per second.
</details>

2. Why does a change of A and B in the same clock count as an error?

<details><summary>Answer</summary>
In correct quadrature only one of the two changes at a time. Both at once means the step was too fast to see or there was noise: the direction cannot be known.
</details>

3. How fast may the encoder go before the 0.2 us filter swallows real edges?

<details><summary>Answer</summary>
Edges must be at least 0.2 us apart: up to 5 million edges per second, far beyond any knob or most motor encoders.
</details>

# Ideas

- A menu knob for the VGA project, a volume knob for the radio.
- Motor position control together with project 04 (steppers) or a DC motor with a PWM from the Tools page.

# If something is wrong

- **Counts jump by 2 or go back**: a bouncing knob: raise the filter (`filter_ns=1000`).
- **Wrong direction**: `reverse=True`, or swap A and B.
- **ERRORS rise**: the signals are too fast for the filter, or a wire picks up noise.
