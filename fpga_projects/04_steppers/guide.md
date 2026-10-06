# What it does

Two step/dir outputs for stepper motor drivers (A4988, DRV8825, TMC2208, TB6600) with smooth acceleration: tell an axis "go to position 12000" and the FPGA ramps the speed up, runs at the top speed, and slows down so it stops exactly there. The demo moves axis 0 back and forth and axis 1 at half the speed.

# How it works

A stepper driver makes the motor take one (micro)step for every pulse on STEP, in the direction set by DIR. Fast moves need a **ramp**: a motor that starts at full speed just buzzes and loses steps.

Every microsecond each axis adds its **speed** to a 40-bit phase; every time the phase overflows, one step pulse goes out. Every microsecond the speed also grows by ACCEL until VMAX. The FPGA counts the steps it took while speeding up; when the steps left to the target are that many, it slows down the same way. The result is a trapezoid speed profile with the stop exactly on the target.

```
speed
  |     ______________
  |    /              \
  |   /                \
  |__/                  \__  time
     accelerate  cruise  slow down
```

Because it is hardware, the pulses keep a steady rhythm while Linux is busy, and two axes run at the same time. Each STEP pin is read back at the pad and its pulses are counted (PIN_STEPS): the self-test proves every step really left the board.

# Try it

1. Driver **STEP** to J8 pin 5, **DIR** to J8 pin 11 (axis 1: pins 12 and 15), driver logic **GND** to pin 1, driver **VDD** (logic) to 3.3 V.
2. The motor supply (12 to 24 V) goes to the driver only. Set the driver's current limit first.
3. Set the microsteps on the driver (the demo assumes 200 x 16 = 3200 steps per turn).
4. **Upload and run**.

# Program it

```python
from blocks import Bus, Stepper
ax = Stepper(Bus(), slot=1, axis=0)
ax.setup(max_speed=8000, accel=20000, start_speed=200)   # steps/s, steps/s^2, steps/s
ax.move_to(3200)          # one turn at 16 microsteps
ax.wait()
ax.move(-1600)            # half a turn back
ax.stop()                 # slow down and stop (stop(now=True): at once)
print(ax.position(), ax.pin_steps())
```

## Registers (slot 1, axis n at word 16n)

| Word | Name | Meaning |
|---|---|---|
| +0 | TARGET | where to go (writing it starts the move) |
| +1 | POSITION | where the axis is |
| +2, +3 | VMAX | top speed (40 bits) |
| +4, +5 | ACCEL, VSTART | speed change per us, start speed |
| +6, +7 | STATUS, SPEED | moving, direction, slowing down; the speed now |
| +8 | PULSE | step pulse length (2 us) |
| +9 | STOP | 1 slow down and stop, 2 stop at once |
| +10 | PIN_STEPS | steps counted at the STEP pin |
| +11 | DIR_SETUP | time between a direction change and the next step |
| 64 | ID | "STEP" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Phase accumulator for exact step rates | a 40-bit phase plus the speed every microsecond |
| Acceleration ramps (trapezoid profile) | speed grows by ACCEL until VMAX, the same way down |
| Planning the stop in hardware | the steps used to speed up = the steps needed to slow down |
| Proving every pulse left the board | STEP pins read back at their pads (PIN_STEPS) |

## Exercises

1. Why does a stepper motor that starts at full speed often just buzz?

<details><summary>Answer</summary>
The rotor cannot follow a sudden fast pulse train: its inertia needs a few milliseconds of rising speed. Without a ramp it misses steps and stalls.
</details>

2. The axis speeds up for 1200 steps and the move is 2000 steps. How many steps at full speed?

<details><summary>Answer</summary>
Slowing down takes as many steps as speeding up: 2000 - 2 x 1200 is negative, so it never reaches VMAX: it speeds up for 1000 steps and slows down for 1000 (a triangle profile).
</details>

3. A 200-step motor with 1/16 microstepping should turn 3 times per second. What step rate?

<details><summary>Answer</summary>
200 x 16 x 3 = 9600 steps per second.
</details>

# Ideas

- A camera slider, a plotter with two axes, a turntable for 3D scanning.
- Home switch: read a pin, stop, `position(0)`.
- An encoder (project 03) on the motor shaft to check for lost steps.

# If something is wrong

- **The motor buzzes but does not turn**: too fast a start: lower `start_speed` and `accel`, or raise the driver's current.
- **Wrong direction**: swap one coil pair, or use negative targets.
- **The driver gets very hot**: lower its current limit; TMC2208 drivers run cooler.
