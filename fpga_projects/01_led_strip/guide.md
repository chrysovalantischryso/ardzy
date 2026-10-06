# What it does

Drives a strip of addressable RGB LEDs (WS2812B, WS2812, SK6812, "NeoPixel") from J7 pin 5: up to 1024 LEDs, any colour per LED, a brightness setting, and the colour order of your strip. The demo plays a rainbow, a colour wipe, a theatre chase and a breathing glow.

# How it works

A WS2812 strip has one data wire. Every LED takes the first 24 bits it sees (8 green, 8 red, 8 blue), keeps them, and passes the rest on to the next LED. A bit is a high pulse in a 1.25 us slot: a **short** pulse (0.4 us) is a 0, a **long** one (0.8 us) is a 1. A pause of more than 50 us (here 300 us) means "show the colours now".

The timing is tight (+-0.15 us), which is hard for Linux on the ARM but easy for the FPGA: a counter at 100 MHz makes every edge to 10 ns.

```
ARM writes pixels -> pixel memory (1024 words) -> brightness, colour order -> bit timer -> J7 pin 5
                                                        pin read back at the pad -> pulse counter
```

The FPGA also reads its own pin back: it counts the high pulses and measures the short and long ones. The self-test uses that to prove the real signal at the pin is right.

# Try it

1. Strip **DIN** to J7 pin 5, strip **GND** to pin 1 (GND). The strip needs its own 5 V supply (60 mA per LED at full white); connect its ground to the board's ground.
2. Most WS2812B strips take the 3.3 V signal. If yours flickers, add a level shifter (74AHCT125) or power the first LED from 4.5 V (a diode in its supply).
3. **Upload and run**. Change `N` in main.py to the number of LEDs on your strip.

# Program it

```python
from blocks import Bus, LedStrip, rgb, wheel
strip = LedStrip(Bus(), slot=1, count=60)
strip.order('GRB')                   # WS2812B; many SK6812 are GRB too
strip.brightness(64)                 # 0..255: saves power and eyes
strip.fill(rgb(255, 80, 0))          # all orange
strip.set(0, 0x0000FF)               # LED 0 blue
strip.show()                         # send
strip.write([wheel(i * 4) for i in range(60)])   # a rainbow, then show() again
```

`pin_stats()` returns the pulses the FPGA saw at the pin in the last frame. For SK6812 use `strip.timing(300, 600, 1250, 80)`.

## Registers (slot 1, pixels in slot 2)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | write 1: send; read [0] busy, [31:8] frames sent |
| 1 | COUNT | number of LEDs, 1..1024 |
| 2 | BRIGHT | brightness 0..255 |
| 3 | ORDER | 0 GRB, 1 RGB, 2 BRG, 3 RBG, 4 BGR, 5 GBR |
| 4..7 | T0H, T1H, TBIT, TRESET | timing in 10 ns clocks |
| 8..10 | PULSES, HI0, HI1 | measured at the pin |
| 11 | ID | "WS28" |

A frame of 60 LEDs takes 60 x 24 x 1.25 us + 300 us = 2.1 ms: more than 400 frames per second are possible.

# Learn from it

| Idea | Where to see it |
|---|---|
| Exact pulse timing from a counter | the bit timer: 40 clocks for a short pulse, 80 for a long one, 125 per bit |
| A protocol that is only timing (no clock wire) | WS2812: the pulse width is the bit |
| Memory feeding a serial output | the pixel memory read word by word, 24 bits shifted out per LED |
| Checking your own output | the pin read back at the pad, its pulses counted and measured |

## Exercises

1. A strip of 300 LEDs: how long does one update take? (24 bits per LED, 1.25 us per bit, plus the 300 us reset)

<details><summary>Answer</summary>
300 x 24 x 1.25 us = 9 ms, plus 0.3 ms: about 9.3 ms, so up to about 100 updates per second.
</details>

2. Why can Python on Linux not make this signal itself by toggling a pin?

<details><summary>Answer</summary>
A pulse must be 0.4 or 0.8 us with +-0.15 us. Linux can pause any program for tens of microseconds at any moment; one pause ruins a frame. The FPGA's counter is exact to 10 ns.
</details>

3. SK6812 RGBW strips have a fourth (white) byte. What would change in the design?

<details><summary>Answer</summary>
32 bits per LED instead of 24: the shift counter counts to 32 and each pixel word carries the white byte too.
</details>

# Ideas

- A clock, a VU meter with the audio project, a level for the encoder knob.
- More strips: add more `ardzy_ws2812` blocks on other pins (one per slot pair) in a copy of the project.

# If something is wrong

- **First LED wrong, the rest dark**: the 3.3 V level is too low for your strip: level shifter.
- **Colours swapped**: set the colour order (`strip.order('RGB')`).
- **Flicker at full white**: the supply is too weak, or the strip's ground is not connected to the board's ground.
