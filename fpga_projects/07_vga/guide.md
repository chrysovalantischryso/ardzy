# What it does

Shows a picture on any VGA monitor or TV: 640 x 480 at 60 Hz, made from a 320 x 240 frame buffer with 16 colours (chosen from 64). Python draws pixels, lines, rectangles and text into it. The demo is a status screen: the board's temperature as a graph, a clock and colour bars.

# How it works

A VGA monitor draws the picture line by line, like an old TV. The board sends three analog colour signals (red, green, blue) and two sync pulses: **HSYNC** starts a new line (31.25 kHz), **VSYNC** a new frame (59.5 Hz). The timing is fixed: 800 pixel clocks per line (640 visible), 525 lines per frame (480 visible), a pixel clock of 25 MHz.

```
MMCM: 100 MHz x 10 / 40 = 25 MHz pixel clock
  -> pixel and line counters -> HSYNC, VSYNC
  -> frame buffer (block RAM, 320 x 240 x 4 bits) -> palette (16 x 6 bits) -> 2 bits per colour -> resistors -> monitor
```

Each frame-buffer pixel is shown as 2 x 2 screen pixels. The palette turns a 4-bit value into a colour with 2 bits of red, green and blue. Two resistors per colour make the voltage: a 2-bit DAC (470 ohm for the high bit, 1 kohm for the low bit, into the monitor's 75 ohm input).

The frame buffer is a dual-port block RAM: the ARM writes, the picture side reads at the same time. The sync pins are read back at their pads and their periods are measured (HS_PERIOD, VS_PERIOD). PROBE tells which colour the picture shows at any screen point: that is how the self-test checks the picture without a camera.

# Try it

| VGA connector (DE-15) | Board |
|---|---|
| 1 red | J6 pin 5 through 470 ohm, J6 pin 11 through 1 kohm |
| 2 green | J6 pin 12 through 470 ohm, J6 pin 15 through 1 kohm |
| 3 blue | J8 pin 5 through 470 ohm, J8 pin 11 through 1 kohm |
| 13 HSYNC | J8 pin 12 (through 100 ohm) |
| 14 VSYNC | J8 pin 15 (through 100 ohm) |
| 5, 6, 7, 8, 10 ground | GND |

**Upload and run**. A breakout board for the VGA connector makes the wiring easy.

# Program it

```python
from blocks import Bus, VGA
v = VGA(Bus(), slot=1)
v.on()
v.clear(0)
v.palette(1, 3, 3, 3)                 # colour 1 = white (r, g, b each 0..3)
v.rect(10, 10, 100, 40, 2)
v.line(0, 239, 319, 0, 3)
v.text(20, 60, 'Hello Ardzy', 1, scale=2)
v.show()                              # send the picture to the frame buffer
print(v.sync_check())
```

Drawing happens in a copy in Python; `show()` sends it (or `show((y0, y1))` only some rows).

## Registers (slot 1, frame buffer in slots 2..11)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] picture on [1] test pattern |
| 1..3 | FRAMES, HS_PERIOD, VS_PERIOD | (read) measured at the pins |
| 4 | ID | "VGA6" |
| 5, 6 | PROBE_XY, PROBE | what the screen shows at (x, y) |
| 16..31 | palette | [5:4] red [3:2] green [1:0] blue |

# Learn from it

| Idea | Where to see it |
|---|---|
| A clock made inside the FPGA (MMCM) | 100 MHz x 10 / 40 = 25 MHz pixel clock |
| Video timing from two counters | 800 clocks per line, 525 lines per frame, sync pulses at fixed counts |
| A dual-port frame buffer | the ARM writes, the screen side reads, at the same time |
| A resistor DAC | 470 ohm + 1 kohm make 4 levels per colour |

## Exercises

1. How many bytes does the frame buffer need (320 x 240 pixels, 4 bits each)?

<details><summary>Answer</summary>
320 x 240 x 4 / 8 = 38 400 bytes: about 10 block RAMs of the 60.
</details>

2. Why 25 MHz? (800 x 525 clocks per frame at about 60 frames per second)

<details><summary>Answer</summary>
800 x 525 x 60 = 25.2 million pixel clocks per second: the VGA standard's 25.175 MHz; 25.0 MHz gives 59.5 Hz, which monitors accept.
</details>

3. How would you draw a moving ball without the ARM?

<details><summary>Answer</summary>
Compare the pixel counters with the ball's position registers: inside the square -> white. Update the position once per frame (at VSYNC). No frame buffer needed: that is how Pong was built.
</details>

# Ideas

- A dashboard for the radio (frequency, RDS, meters) or the sensors.
- Pong with two encoders (project 03).
- More colours: 3 or 4 resistors per colour.

# If something is wrong

- **"Out of range" or no picture**: check HSYNC and VSYNC; the self-test measures them. Some monitors want 25.175 MHz exactly; most take 25.0.
- **Wrong colours**: a resistor on the wrong pin, or palette entries changed.
