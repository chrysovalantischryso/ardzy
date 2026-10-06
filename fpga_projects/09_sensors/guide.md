# What it does

Three sensors that need exact timing, measured by the FPGA: an **HC-SR04** ultrasonic distance sensor, an **IR remote** receiver (NEC codes, most cheap remotes) and a **capacitive touch** pad made of a wire or a coin. The demo prints distance, remote buttons and touches as they happen; LED 0 lights while the pad is touched.

# How it works

## Distance (HC-SR04)

The FPGA sends a 10 us pulse on TRIG every 60 ms. The sensor sends 8 ultrasonic pulses and raises ECHO until the sound comes back. The FPGA times ECHO to the microsecond:

```
distance in mm = echo time in us x 343 / 2000      (sound at 20 C: 343 m/s, there and back)
```

No echo within 38 ms means "nothing in range" (more than about 4 m). An **echo simulator** inside can stand in for the sensor (the self-test uses it).

## IR remote (NEC)

A remote flashes infrared light at 38 kHz; a receiver module (VS1838B, TSOP38238) turns the flashes into a clean low signal. The NEC code: a 9 ms start pulse, a 4.5 ms gap, then 32 bits (address, inverted address, command, inverted command), each bit a 0.56 ms pulse followed by a short (0 bit) or long (1 bit) gap. Holding a button sends **repeat codes**. The FPGA measures every gap, checks the inverted copies, and counts codes, repeats and errors. An IR transmitter inside the FPGA can send a test code to the decoder.

## Touch

The pin pulls its wire low, lets go, and counts how long the 1 Mohm resistor to 3.3 V takes to charge it until it reads high: a few microseconds. A finger adds capacitance, so it takes longer. The base level follows slow changes (temperature, humidity); a difference above TOUCH_DIFF is a touch.

# Try it

| Sensor | Wiring |
|---|---|
| HC-SR04 | VCC 5 V, GND, TRIG to J8 pin 5, ECHO to J8 pin 11 **through a divider** (1 k to the pin, 2 k from the pin to GND): ECHO is 5 V! |
| IR receiver | OUT to J8 pin 12, VCC 3.3 V, GND |
| touch pad | a wire or a coin on J8 pin 15, and a 1 Mohm resistor from J8 pin 15 to 3.3 V |

**Upload and run**, then wave a hand in front of the sensor, press remote buttons, touch the pad.

# Program it

```python
from blocks import Bus, Sensors
s = Sensors(Bus(), slot=1)
s.setup(distance=True, touch=True)
print(s.distance_mm())        # None when nothing is in range
print(s.ir())                 # {'count', 'repeats', 'errors', 'address', 'command', ...}
print(s.touch())              # {'raw', 'base', 'touched', 'touches'}
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] distance [1] echo simulator [2] touch [3] IR test |
| 1 | PERIOD | time between measurements |
| 2..5 | ECHO_US, DIST_MM, RANGINGS, TIMEOUTS | (read) |
| 6 | SIM_US | echo simulator |
| 7..10 | IR_CODE, IR_COUNT, IR_REPEATS, IR_ERRORS | (read) |
| 11 | TEST_CODE | the IR test code |
| 12..15 | TOUCH_RAW, TOUCH_BASE, TOUCHED, TOUCH_DIFF | touch |
| 16 | ID | "SENS" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Timing a pulse to the microsecond | the ECHO pin's high time |
| Decoding a protocol from pulse lengths | NEC IR: a 0 and a 1 differ only in the gap after the pulse |
| Measuring capacitance by charge time | touch: how long a 1 Mohm resistor takes to charge the pin |
| Simulators inside the design | an echo simulator stands in for the sensor in the self-test |

## Exercises

1. The echo lasts 5830 us. How far is the object?

<details><summary>Answer</summary>
5830 x 343 / 2000 = 1000 mm: one metre.
</details>

2. Why does the NEC code send the address and the command twice, the second time inverted?

<details><summary>Answer</summary>
To catch errors: a byte and its inverse always add up to 0xFF. A disturbed bit breaks that and the code is thrown away.
</details>

3. Why does the touch sensor follow a slowly changing base level?

<details><summary>Answer</summary>
Humidity, temperature and the cable change the charge time slowly. A touch is a quick, big change on top of that; tracking the base keeps one threshold working all day.
</details>

# Ideas

- A parking sensor with the LED strip (project 01) as a bar, or a beeper.
- Control the radio (project 12) with a TV remote: next song, volume.
- A theremin: the distance sets the pitch of the audio project's tone.

# If something is wrong

- **Distance always None**: the divider on ECHO is missing a ground, or the sensor has no 5 V.
- **Jumping distances**: soft or slanted surfaces scatter the sound; measure flat, hard things.
- **IR codes with errors**: the receiver needs 3.3 V and a clean supply (a 100 nF capacitor at its pins helps); some remotes are not NEC (RC5, Sony).
- **Touch too sensitive / not enough**: change TOUCH_DIFF (`s.touch_threshold(clocks)`).
