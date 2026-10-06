# What it does

A digital pattern generator: the opposite of a logic analyzer. It plays a table of up to 1024 steps on 16 pins (J5 to J8), one step every 10 ns up to every 43 s, once or over and over. Use it to make test signals: clocks, counters, serial data, PWM, stepper sequences, a fake sensor for another board.

# How it works

The ARM writes the table into a block RAM in the FPGA: word n holds the levels of the 16 pins for step n (bit k = pin k). A counter divides the 100 MHz clock: every DIV + 1 clocks the next word goes to the pins. At DIV = 0 that is 100 million steps per second, far faster than any program on a processor can toggle pins, and with no jitter.

```
table (block RAM) -> step counter (DIV) -> output register -> 16 pins
                                       pins read back at the pads -> MISMATCH counter
```

Each output is also read back at its pad: the FPGA compares what the pin shows with what it should show and counts the differences (MISMATCH). A short circuit or another device driving the pin shows up there.

| Pin bit | Connector |
|---|---|
| 0..3 | J5 pins 5, 11, 12, 15 |
| 4..7 | J6 pins 5, 11, 12, 15 |
| 8..11 | J7 pins 5, 11, 12, 15 |
| 12..15 | J8 pins 5, 11, 12, 15 |

# Try it

**Upload and run**: the demo plays a few patterns (a binary counter, a walking 1, a burst). Look at them with a scope, or with the **Tools** page's logic analyzer on another board, or with a cheap USB logic analyzer (and PulseView).

# Program it

```python
from blocks import Bus, PatternGen
pg = PatternGen(Bus(), slot=1)
pg.outputs(0xFFFF)                       # all 16 pins are outputs
pg.load([i for i in range(256)])         # an 8-bit counter on pins 0..7
pg.rate(1_000_000)                       # 1 million steps per second
pg.start(loop=True)
print(pg.status())                       # step, loops, mismatches
pg.stop()
```

A UART byte at 9600 baud on pin 0: `pg.rate(9600)`, then the bits of `[0] + data bits (LSB first) + [1]` as steps.

## Registers (slot 1, the table in slot 2)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] run (start from step 0), [1] loop |
| 1 | LENGTH | steps, 1..1024 |
| 2 | DIV | clocks per step minus 1 |
| 3 | OE | output enable per pin |
| 4 | IDLE | levels when stopped |
| 5..8 | STEP, LOOPS, MISMATCH, INPUTS | (read) |
| 9 | ID | "PATG" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Block RAM as a pattern table | one word per step, bit k = pin k |
| A divider sets the speed | DIV + 1 clocks per step: 100 million steps per second at DIV = 0 |
| No jitter: hardware timing | every edge exactly on a 10 ns clock edge |
| Self-checking outputs | each pin read back at its pad, differences counted in MISMATCH |

## Exercises

1. You want a 1 MHz square wave on pin 0 with a 2-step table (1, 0). What DIV?

<details><summary>Answer</summary>
Each step lasts DIV + 1 clocks and a period is 2 steps: 2 x (DIV + 1) x 10 ns = 1 us, so DIV = 49.
</details>

2. How would you make a 4-phase stepper motor sequence on pins 0..3?

<details><summary>Answer</summary>
A 4-step table: 0b0001, 0b0010, 0b0100, 0b1000 (or 8 half steps), looping, with DIV setting the step rate.
</details>

3. MISMATCH counts up while a pin is shorted to ground. Why is that useful?

<details><summary>Answer</summary>
The FPGA notices that the pin does not show what it drives: a wiring error, a short or two drivers fighting are found without a scope.
</details>

# Ideas

- Drive a 7-segment display, a shift register (74HC595) or an R-2R ladder (a slow waveform).
- Make the test signals for another project: encoder A/B signals for project 03, step/dir for a motor driver.

# If something is wrong

- **MISMATCH counts up**: something else drives the pin, or the pin is shorted. Pins set as inputs (OE bit 0) are not checked.
- **Edges look slow on a scope at 100 MHz**: that is the pin and the probe; use short wires and the scope's 10x probe.
