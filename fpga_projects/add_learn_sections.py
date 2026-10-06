"""Adds a "Learn from it" section (key ideas, where to see them, exercises with answers) to the guides of the
first 12 ready projects, just before their "# Ideas" heading. Safe to run again: a guide that already has the
section is left alone.

    python add_learn_sections.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def ex(n, task, answer):
    return '%d. %s\n\n<details><summary>Answer</summary>\n%s\n</details>\n' % (n, task, answer)


LEARN = {
'01_led_strip': ("""| Idea | Where to see it |
|---|---|
| Exact pulse timing from a counter | the bit timer: 40 clocks for a short pulse, 80 for a long one, 125 per bit |
| A protocol that is only timing (no clock wire) | WS2812: the pulse width is the bit |
| Memory feeding a serial output | the pixel memory read word by word, 24 bits shifted out per LED |
| Checking your own output | the pin read back at the pad, its pulses counted and measured |
""", [
("A strip of 300 LEDs: how long does one update take? (24 bits per LED, 1.25 us per bit, plus the 300 us reset)",
 "300 x 24 x 1.25 us = 9 ms, plus 0.3 ms: about 9.3 ms, so up to about 100 updates per second."),
("Why can Python on Linux not make this signal itself by toggling a pin?",
 "A pulse must be 0.4 or 0.8 us with +-0.15 us. Linux can pause any program for tens of microseconds at any moment; one pause ruins a frame. The FPGA's counter is exact to 10 ns."),
("SK6812 RGBW strips have a fourth (white) byte. What would change in the design?",
 "32 bits per LED instead of 24: the shift counter counts to 32 and each pixel word carries the white byte too."),
]),
'02_pattern_gen': ("""| Idea | Where to see it |
|---|---|
| Block RAM as a pattern table | one word per step, bit k = pin k |
| A divider sets the speed | DIV + 1 clocks per step: 100 million steps per second at DIV = 0 |
| No jitter: hardware timing | every edge exactly on a 10 ns clock edge |
| Self-checking outputs | each pin read back at its pad, differences counted in MISMATCH |
""", [
("You want a 1 MHz square wave on pin 0 with a 2-step table (1, 0). What DIV?",
 "Each step lasts DIV + 1 clocks and a period is 2 steps: 2 x (DIV + 1) x 10 ns = 1 us, so DIV = 49."),
("How would you make a 4-phase stepper motor sequence on pins 0..3?",
 "A 4-step table: 0b0001, 0b0010, 0b0100, 0b1000 (or 8 half steps), looping, with DIV setting the step rate."),
("MISMATCH counts up while a pin is shorted to ground. Why is that useful?",
 "The FPGA notices that the pin does not show what it drives: a wiring error, a short or two drivers fighting are found without a scope."),
]),
'03_encoders': ("""| Idea | Where to see it |
|---|---|
| Quadrature decoding: direction from edge order | A leads B one way, B leads A the other |
| Glitch filtering | a level is taken only after 0.2 us without change |
| Counting in hardware never misses | every edge seen at 100 MHz |
| A test generator inside the design | A/B signals made by the FPGA to test its own counters |
""", [
("An encoder with 24 lines turns once per second. How many counts per second?",
 "Every edge of A and B counts: 4 x 24 = 96 counts per second."),
("Why does a change of A and B in the same clock count as an error?",
 "In correct quadrature only one of the two changes at a time. Both at once means the step was too fast to see or there was noise: the direction cannot be known."),
("How fast may the encoder go before the 0.2 us filter swallows real edges?",
 "Edges must be at least 0.2 us apart: up to 5 million edges per second, far beyond any knob or most motor encoders."),
]),
'04_steppers': ("""| Idea | Where to see it |
|---|---|
| Phase accumulator for exact step rates | a 40-bit phase plus the speed every microsecond |
| Acceleration ramps (trapezoid profile) | speed grows by ACCEL until VMAX, the same way down |
| Planning the stop in hardware | the steps used to speed up = the steps needed to slow down |
| Proving every pulse left the board | STEP pins read back at their pads (PIN_STEPS) |
""", [
("Why does a stepper motor that starts at full speed often just buzz?",
 "The rotor cannot follow a sudden fast pulse train: its inertia needs a few milliseconds of rising speed. Without a ramp it misses steps and stalls."),
("The axis speeds up for 1200 steps and the move is 2000 steps. How many steps at full speed?",
 "Slowing down takes as many steps as speeding up: 2000 - 2 x 1200 is negative, so it never reaches VMAX: it speeds up for 1000 steps and slows down for 1000 (a triangle profile)."),
("A 200-step motor with 1/16 microstepping should turn 3 times per second. What step rate?",
 "200 x 16 x 3 = 9600 steps per second."),
]),
'05_spi_i2c': ("""| Idea | Where to see it |
|---|---|
| Shift registers: send and receive at the same time | SPI: every SCLK edge shifts a bit out and a bit in |
| Clock polarity and phase (modes 0..3) | CPOL, CPHA in the control register |
| Open-drain buses shared by many devices | I2C: devices only pull low, resistors pull high |
| A command queue between software and exact timing | the ARM queues START, WRITE, READ, STOP; the FPGA runs them |
""", [
("SPI at DIV = 4: what clock frequency, and how long for a 16-bit word?",
 "100 MHz / (2 x 5) = 10 MHz; 16 bits take 1.6 us."),
("Why must I2C lines be open drain with pull-up resistors?",
 "Several devices share one wire. If any could drive it high while another drives it low, they would short. With open drain they can only pull low; the resistor makes high. Clock stretching and acknowledges work because anyone may hold a line low."),
("An I2C device does not answer its address. What does the master see?",
 "No ACK: SDA stays high (the pull-up) in the ninth clock. The FPGA reports a NACK; usually a wrong address, a missing pull-up or a device without power."),
]),
'06_signal_gen': ("""| Idea | Where to see it |
|---|---|
| Direct digital synthesis | a 32-bit phase + FREQ every clock, a 1024-point sine table |
| Digital to analog without a DAC chip | sigma-delta and PWM outputs plus an RC low-pass |
| An R-2R ladder DAC | 8 pins and 8 + 8 resistors make an 8-bit analog output |
| Measuring your own output | the frequency at the sync pin, read back at the pad |
""", [
("What FREQ gives 440 Hz (the note A)?",
 "440 x 2^32 / 100 000 000 = 18 898 (18 897.7 rounded): the real frequency is 440.003 Hz."),
("A 1 kohm and 10 nF low-pass: what is its corner frequency, and why does it suit the sigma-delta output?",
 "1 / (2 pi R C) = 15.9 kHz: it keeps audio but removes the 100 MHz switching of the bit stream."),
("Why is an R-2R ladder good to several MHz while the sigma-delta is clean only to about 20 kHz?",
 "The ladder outputs the whole 8-bit value at once every clock; the sigma-delta needs many clocks of 1-bit pulses averaged by a slow filter to make one value."),
]),
'07_vga': ("""| Idea | Where to see it |
|---|---|
| A clock made inside the FPGA (MMCM) | 100 MHz x 10 / 40 = 25 MHz pixel clock |
| Video timing from two counters | 800 clocks per line, 525 lines per frame, sync pulses at fixed counts |
| A dual-port frame buffer | the ARM writes, the screen side reads, at the same time |
| A resistor DAC | 470 ohm + 1 kohm make 4 levels per colour |
""", [
("How many bytes does the frame buffer need (320 x 240 pixels, 4 bits each)?",
 "320 x 240 x 4 / 8 = 38 400 bytes: about 10 block RAMs of the 60."),
("Why 25 MHz? (800 x 525 clocks per frame at about 60 frames per second)",
 "800 x 525 x 60 = 25.2 million pixel clocks per second: the VGA standard's 25.175 MHz; 25.0 MHz gives 59.5 Hz, which monitors accept."),
("How would you draw a moving ball without the ARM?",
 "Compare the pixel counters with the ball's position registers: inside the square -> white. Update the position once per frame (at VSYNC). No frame buffer needed: that is how Pong was built."),
]),
'08_audio': ("""| Idea | Where to see it |
|---|---|
| Deriving clocks by division | MCLK, BCLK and LRCLK all from 100 MHz |
| A FIFO absorbs the software's irregular timing | 2048 samples = 42 ms in hand |
| Serial audio (I2S) | DATA most significant bit first, LRCLK selects the channel |
| Turning 1-bit PDM into samples | a CIC filter: sums and differences |
""", [
("Why can the board's I2S run at 48 828 Hz instead of 48 000 Hz?",
 "100 MHz / 2048 = 48 828.125 Hz is a whole divider of the clock; DACs with their own PLL lock to whatever LRCLK they get. Python resamples the sound to match."),
("The FIFO holds 2048 samples. How long may Python pause before the sound breaks?",
 "2048 / 48 828 = 42 ms: any pause shorter than that (minus what is still in the FIFO) is heard as nothing."),
("A PDM microphone sends 3.125 million bits per second. Why does a filter turn them into sound?",
 "The density of ones follows the air pressure. A low-pass filter averages the bits: the average is the sound sample; decimating by 64 gives 48.8 kHz."),
]),
'09_sensors': ("""| Idea | Where to see it |
|---|---|
| Timing a pulse to the microsecond | the ECHO pin's high time |
| Decoding a protocol from pulse lengths | NEC IR: a 0 and a 1 differ only in the gap after the pulse |
| Measuring capacitance by charge time | touch: how long a 1 Mohm resistor takes to charge the pin |
| Simulators inside the design | an echo simulator stands in for the sensor in the self-test |
""", [
("The echo lasts 5830 us. How far is the object?",
 "5830 x 343 / 2000 = 1000 mm: one metre."),
("Why does the NEC code send the address and the command twice, the second time inverted?",
 "To catch errors: a byte and its inverse always add up to 0xFF. A disturbed bit breaks that and the code is thrown away."),
("Why does the touch sensor follow a slowly changing base level?",
 "Humidity, temperature and the cable change the charge time slowly. A touch is a quick, big change on top of that; tracking the base keeps one threshold working all day."),
]),
'10_riscv': ("""| Idea | Where to see it |
|---|---|
| What a processor is: fetch, decode, execute | the multi-cycle core, about 5 clocks per instruction |
| Memory-mapped peripherals | LEDs, GPIO, console at 0x8000_0000 |
| Shared memory between two processors | the ARM reads and writes the RISC-V's RAM while it runs |
| Machine code | `blink.s`, `primes.s` and the assembler in `riscv.py` |
""", [
("At about 5 clocks per instruction and 100 MHz, how long does a loop of 4 instructions take, 1 million times?",
 "4 x 5 x 10 ns x 1 000 000 = 0.2 s."),
("Why is this slow core still useful next to two 667 MHz ARM cores?",
 "It is exactly predictable: no caches, no operating system, no interrupts it did not ask for. A loop always takes the same time, to the nanosecond: good for precise control and for learning."),
("How does the ARM send a number to a running RISC-V program?",
 "It writes MAIL_IN (or any shared RAM word); the program polls the address and reads it. MAIL_OUT works the other way."),
]),
'11_stream_lab': ("""| Idea | Where to see it |
|---|---|
| Handshake: data moves only when valid and ready | tvalid / tready on every stream |
| Back pressure | the meter takes a word only every n clocks; nothing is lost |
| FIFOs decouple producers and consumers | `ardzy_axis_fifo` between every pair of blocks |
| Frames and arbitration | tlast marks the end of a frame; the arbiter never splits one |
""", [
("A source offers 100 million words per second, the sink takes 1 in 4 clocks. What happens to the source?",
 "It sees tready low 3 clocks in 4 and waits: 25 million words per second pass, none lost. That is back pressure."),
("Why does CRC-32 detect any single changed bit in a frame?",
 "CRC is the remainder of a polynomial division; a single changed bit adds a term the generator polynomial cannot divide, so the remainder always changes."),
("Why must a block never lower tvalid or change tdata before the word is taken?",
 "The sink may take it at any later clock; changing it early would lose or corrupt that word. The rule makes any two blocks safe to connect."),
]),
'12_fm_radio': ("""| Idea | Where to see it |
|---|---|
| A numerically controlled oscillator | the 32-bit RF phase at 500 million samples per second |
| Frequency modulation | the MPX signal adds to the phase step |
| Stereo multiplex | L+R, a 19 kHz pilot, L-R on 38 kHz, RDS on 57 kHz |
| Digital data on a radio signal | RDS: groups, check words, biphase symbols |
""", [
("FM broadcast deviates +-75 kHz. With a 32-bit phase at 500 MHz, how big is the phase step change for 75 kHz?",
 "75 000 x 2^32 / 500 000 000 = 644 245 steps: the MPX value is scaled to that at full level."),
("Why is the stereo pilot exactly 19 kHz, half of the 38 kHz subcarrier?",
 "The receiver doubles the pilot to rebuild the 38 kHz carrier in exact phase, and demodulates L-R with it. RDS at 57 kHz is the third harmonic, locked too."),
("RDS sends 1187.5 bits per second. How long does a station name (4 groups of 104 bits) take?",
 "416 bits / 1187.5 = 0.35 s; in practice the name is sent between other groups, so receivers show it within a second or two."),
]),
}


def main():
    for name, (table, exercises) in LEARN.items():
        p = os.path.join(HERE, name, 'guide.md')
        s = open(p, encoding='utf-8').read()
        if '# Learn from it' in s:
            print('%-16s already has it' % name)
            continue
        section = '# Learn from it\n\n' + table + '\n## Exercises\n\n' + '\n'.join(ex(i + 1, t, a) for i, (t, a) in enumerate(exercises)) + '\n'
        i = s.find('\n# Ideas')
        s = s[:i + 1] + section + s[i + 1:] if i >= 0 else s.rstrip() + '\n\n' + section
        open(p, 'w', encoding='utf-8', newline='\n').write(s)
        print('%-16s section added' % name)


if __name__ == '__main__':
    main()
