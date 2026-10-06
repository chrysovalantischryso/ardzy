"""Writes the lesson projects of the Learn course into pc_app/templates/learn_NN_*.

    python learn/make_templates.py

Every lesson project: top.v (the design, explained line by line), main.py (first it checks the hardware and prints
RESULT: n of m ok, then a demo you can change) and the pin constraints it needs. The app's Learn view creates
a project from them with one click.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, '..', 'templates')

LEDS_XDC = """# The 4 LEDs of the board, driven by the FPGA. ACTIVE LOW: an LED lights when its pin is 0.
set_property PACKAGE_PIN F16 [get_ports {leds[0]}]
set_property PACKAGE_PIN L19 [get_ports {leds[1]}]
set_property PACKAGE_PIN M19 [get_ports {leds[2]}]
set_property PACKAGE_PIN M17 [get_ports {leds[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {leds[*]}]
"""

CHECK_PY = '''results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('CHECK %-4s %-48s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)
'''

LESSONS = {}

# ------------------------------------------------------------------------------------------------ 1
LESSONS['learn_01_logic'] = {
'top.v': r'''// Lesson 1: logic gates. The ARM sets three inputs a, b, c; the FPGA computes four functions of them
// and shows them on the LEDs. Nothing here has a clock: it is pure logic, the answer changes as soon as the
// inputs change (a few nanoseconds later).
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds                  // the board's 4 LEDs (active low: 0 = on)
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // register 0, written by the ARM at 0x4120_0000
    wire [31:0] status;                     // register 0, read by the ARM at 0x4120_0080
    ardzy_soc #(.N_CTRL(1), .N_STAT(1)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    wire a = ctrl[0];                       // three inputs, from the ARM
    wire b = ctrl[1];
    wire c = ctrl[2];

    wire f_and  = a & b;                    // 1 only when a AND b are 1
    wire f_or   = a | b;                    // 1 when a OR b (or both) is 1
    wire f_xor  = a ^ b;                    // 1 when a and b are DIFFERENT
    wire f_maj  = (a & b) | (a & c) | (b & c);   // 1 when at least two of three are 1 (majority vote)

    wire [3:0] f = {f_maj, f_xor, f_or, f_and};
    assign leds   = ~f;                     // invert: the LED pins are active low
    assign status = {28'd0, f};             // the ARM can read the answers back
endmodule
''',
'main.py': r'''# Lesson 1: logic gates. Python sets the inputs a, b, c; the FPGA answers with AND, OR, XOR and MAJORITY.
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)                  # the design's registers (ardzy_soc)
CTRL, STATUS = 0x00, 0x80

print('Truth table: what the FPGA computes for every input')
print('  a b c | AND OR XOR MAJ')
bad = 0
for n in range(8):
    a, b, c = n & 1, (n >> 1) & 1, (n >> 2) & 1
    regs.write(CTRL, n)                  # the inputs go to the FPGA
    f = regs.read(STATUS)                # its answers come back
    got = [(f >> i) & 1 for i in range(4)]
    want = [a & b, a | b, a ^ b, int(a + b + c >= 2)]
    bad += got != want
    print('  %d %d %d |  %d   %d   %d   %d' % (a, b, c, *got))
check('all 8 rows equal Python\'s logic', bad == 0, '%d wrong' % bad)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nNow the LEDs count through the inputs once a second: watch AND, OR, XOR and MAJ change.')
n = 0
while True:
    regs.write(CTRL, n % 8)
    print('inputs a=%d b=%d c=%d  -> LEDs %s' % (n & 1, (n >> 1) & 1, (n >> 2) & 1, format(regs.read(STATUS), '04b')), flush=True)
    n += 1
    time.sleep(1)
''',
}

# ------------------------------------------------------------------------------------------------ 2
LESSONS['learn_02_counter'] = {
'top.v': r'''// Lesson 2: the clock and a counter. A 32-bit counter adds 1 at every rising edge of the 100 MHz clock.
// Its bits toggle at 50 MHz, 25 MHz, 12.5 MHz ... each bit half as fast as the one before. Bits 23 to 26
// are slow enough to see (about 6, 3, 1.5 and 0.75 blinks per second). The ARM chooses which bits light the LEDs.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl: which bit drives LED 0 (the LEDs show bits n .. n+3)
    wire [63:0] status;                     // status 0: the counter, status 1: rising edges of bit 26
    ardzy_soc #(.N_CTRL(1), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    reg [31:0] count = 32'd0;               // a register: it keeps its value between clock edges
    always @(posedge clk)                   // at every rising edge of the clock ...
        count <= count + 1'b1;              // ... the counter takes its old value + 1

    wire [4:0] n = (ctrl[4:0] > 5'd28) ? 5'd28 : ctrl[4:0];
    assign leds = ~count[n +: 4];           // 4 bits, starting at bit n (default 0: too fast to see!)

    reg [31:0] blinks = 32'd0;              // count how often bit 26 goes from 0 to 1
    reg last26 = 1'b0;
    always @(posedge clk) begin
        last26 <= count[26];
        if (count[26] && !last26) blinks <= blinks + 1'b1;
    end
    assign status = {blinks, count};
endmodule
''',
'main.py': r'''# Lesson 2: the clock and a counter. Python measures how fast the FPGA counts, then picks which bits blink.
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
CTRL, COUNT, BLINKS = 0x00, 0x80, 0x84

c0, t0 = regs.read(COUNT), time.time()
time.sleep(1.0)
c1, t1 = regs.read(COUNT), time.time()
rate = ((c1 - c0) & 0xFFFFFFFF) / (t1 - t0)
print('The counter went from %d to %d in %.3f s: %.1f million counts per second' % (c0, c1, t1 - t0, rate / 1e6))
check('the counter counts at the clock: 100 MHz', abs(rate - 100e6) < 2e6, '%.2f MHz' % (rate / 1e6))
b0 = regs.read(BLINKS)
time.sleep(3.0)
blinks = regs.read(BLINKS) - b0
check('bit 26 toggles 100e6 / 2^27 = 0.745 times per second', 1 <= blinks <= 3, '%d rising edges in 3 s' % blinks)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nThe LEDs show 4 bits of the counter. Bit n blinks 100 000 000 / 2^(n+1) times per second:')
for n in (20, 22, 23, 24):
    regs.write(CTRL, n)
    print('  LEDs = bits %d .. %d  (LED 0 blinks %.1f times per second)' % (n, n + 3, 100e6 / 2 ** (n + 1)), flush=True)
    time.sleep(4)
regs.write(CTRL, 23)
print('Left at bits 23 .. 26: a binary counter you can watch. Change the numbers above and upload again.')
while True:
    time.sleep(1)
''',
}

# ------------------------------------------------------------------------------------------------ 3
LESSONS['learn_03_edges'] = {
'top.v': r'''// Lesson 3: edges, synchronizers and debouncing. A "button" (a bit the ARM sets, or a real button on
// J1 pin 5 to GND) is brought into the clock domain with two flip-flops, cleaned up (debounced) and its
// presses are counted. Each press toggles LED 0; LED 1 shows the button itself.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    input  wire       button_n              // J1 pin 5: a button to GND (the pin has a pull-up: 1 = released)
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl[0]: a "button" pressed by software  ctrl[1]: use the pin too
    wire [63:0] status;                     // status 0: presses counted  status 1: raw changes seen (bounces)
    ardzy_soc #(.N_CTRL(1), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    wire raw = ctrl[0] | (ctrl[1] & ~button_n);

    // 1. Synchronizer: an input that changes at any moment can catch a flip-flop "half way" (metastability).
    //    Two flip-flops in a row give it a whole clock to settle.
    reg s1 = 1'b0, s2 = 1'b0;
    always @(posedge clk) begin s1 <= raw; s2 <= s1; end

    // 2. Debounce: a real button bounces for a few milliseconds. Accept a new level only after it has been
    //    stable for 5 ms (500 000 clocks).
    reg [18:0] stable = 19'd0;
    reg clean = 1'b0;
    reg [31:0] bounces = 32'd0;
    reg s2_last = 1'b0;
    always @(posedge clk) begin
        s2_last <= s2;
        if (s2 != s2_last) bounces <= bounces + 1'b1;
        if (s2 == clean) stable <= 19'd0;
        else if (stable == 19'd499_999) begin clean <= s2; stable <= 19'd0; end
        else stable <= stable + 1'b1;
    end

    // 3. Edge detector: "pressed now and not pressed one clock ago" = a rising edge, high for exactly 1 clock.
    reg clean_last = 1'b0;
    wire press = clean & ~clean_last;
    reg [31:0] presses = 32'd0;
    reg toggle = 1'b0;
    always @(posedge clk) begin
        clean_last <= clean;
        if (press) begin presses <= presses + 1'b1; toggle <= ~toggle; end
    end

    assign leds = ~{2'b00, clean, toggle};
    assign status = {bounces, presses};
endmodule
''',
'main.py': r'''# Lesson 3: edges and debouncing. Python presses a "button" (and makes it bounce); the FPGA counts clean presses.
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
CTRL, PRESSES, BOUNCES = 0x00, 0x80, 0x84

p0 = regs.read(PRESSES)
for i in range(5):
    regs.write(CTRL, 1); time.sleep(0.05)
    regs.write(CTRL, 0); time.sleep(0.05)
check('5 clean presses counted as 5', regs.read(PRESSES) - p0 == 5, '%d' % (regs.read(PRESSES) - p0))

p0, b0 = regs.read(PRESSES), regs.read(BOUNCES)
for i in range(3):                       # a bouncy press: 6 quick changes, then held
    for _ in range(3):
        regs.write(CTRL, 1); regs.write(CTRL, 0)
    regs.write(CTRL, 1); time.sleep(0.05)
    regs.write(CTRL, 0); time.sleep(0.05)
dp, db = regs.read(PRESSES) - p0, regs.read(BOUNCES) - b0
check('3 bouncy presses still count as 3', dp == 3, '%d presses, %d raw changes seen' % (dp, db))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nConnect a button between J1 pin 5 and GND (pin 1) and press it: LED 0 toggles at every press.')
regs.write(CTRL, 2)                      # use the pin
last = regs.read(PRESSES)
while True:
    p = regs.read(PRESSES)
    if p != last:
        print('press %d (raw changes so far: %d: the bounces the debouncer hid)' % (p, regs.read(BOUNCES)), flush=True)
        last = p
    time.sleep(0.05)
''',
'pins.xdc': """# Lesson 3: a button on J1 pin 5 (to GND), with the FPGA's pull-up
set_property PACKAGE_PIN T11 [get_ports {button_n}]
set_property IOSTANDARD LVCMOS33 [get_ports {button_n}]
set_property PULLTYPE PULLUP [get_ports {button_n}]
""",
}

# ------------------------------------------------------------------------------------------------ 4
LESSONS['learn_04_pwm'] = {
'top.v': r'''// Lesson 4: PWM (pulse width modulation). A pin can only be 0 or 1, but switched fast enough the eye (or a
// motor, or a filter) sees the average. Each LED gets its own 8-bit brightness: a counter runs 0..255 and the
// LED is on while the counter is below the brightness. 100 MHz / 256 / 16 = 24 kHz: no flicker.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    output wire       pwm_pin               // J1 pin 11: the PWM of LED 0, for a scope or a logic analyzer
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl: brightness of LED 3, 2, 1, 0 (one byte each)
    wire [31:0] status;                     // status: clocks LED 0 was on during the last 1024 periods
    ardzy_soc #(.N_CTRL(1), .N_STAT(1)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    reg [3:0] pre = 4'd0;                   // divide the clock by 16
    reg [7:0] ramp = 8'd0;                  // the PWM counter: 0, 1, ... 255, 0, ...
    always @(posedge clk) begin
        pre <= pre + 1'b1;
        if (pre == 4'd15) ramp <= ramp + 1'b1;
    end

    wire [3:0] on;
    genvar i;
    generate for (i = 0; i < 4; i = i + 1) begin : ch
        assign on[i] = ramp < ctrl[8 * i +: 8];      // on while the counter is below the brightness
    end endgenerate
    assign leds = ~on;
    assign pwm_pin = on[0];

    // measure: how many clocks was LED 0 on during 1024 PWM periods (= the duty cycle x 4 194 304)
    reg [21:0] window = 22'd0;
    reg [31:0] high = 32'd0, high_last = 32'd0;
    always @(posedge clk) begin
        window <= window + 1'b1;
        if (window == 22'h3FFFFF) begin high_last <= high + on[0]; high <= 32'd0; end
        else if (on[0]) high <= high + 1'b1;
    end
    assign status = high_last;
endmodule
''',
'main.py': r'''# Lesson 4: PWM. Python sets brightness 0..255 per LED; the FPGA measures its own duty cycle.
import math
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
CTRL, HIGH = 0x00, 0x80
WINDOW = 4194304                         # clocks in the measuring window

bad = []
for level in (0, 64, 128, 192, 255):
    regs.write(CTRL, level)
    time.sleep(0.12)
    duty = regs.read(HIGH) / WINDOW
    print('brightness %3d: LED 0 on %5.1f %% of the time (expected %5.1f %%)' % (level, 100 * duty, 100 * level / 256))
    if abs(duty - level / 256) > 0.002:
        bad.append(level)
check('measured duty = brightness / 256', not bad, 'wrong at %s' % bad if bad else '')
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nBreathing LEDs: each LED follows a sine, a quarter period after the one before.')
print('Our eyes see brightness roughly as the logarithm of light: squaring the sine makes the breath look even.')
t0 = time.time()
while True:
    t = time.time() - t0
    v = 0
    for i in range(4):
        s = (math.sin(2 * math.pi * (t / 3 - i / 4)) + 1) / 2
        v |= int(255 * s * s) << (8 * i)
    regs.write(CTRL, v)
    time.sleep(0.02)
''',
'pins.xdc': """# Lesson 4: the PWM of LED 0 also on J1 pin 11
set_property PACKAGE_PIN T12 [get_ports {pwm_pin}]
set_property IOSTANDARD LVCMOS33 [get_ports {pwm_pin}]
""",
}

# ------------------------------------------------------------------------------------------------ 5
LESSONS['learn_05_fsm'] = {
'top.v': r'''// Lesson 5: a state machine (FSM). A traffic light with a pedestrian button. The design is always in one of a
// few STATES; a timer and the button decide when it moves to the next one. LED 0 red, LED 1 yellow,
// LED 2 green, LED 3 "walk". The times are short (seconds) so you can watch it.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl[0]: the pedestrian presses the button (a pulse from the ARM)
    wire [63:0] status;                     // status 0: [2:0] the state, [3] someone waits  status 1: clocks left
    ardzy_soc #(.N_CTRL(1), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    localparam GREEN = 3'd0, YELLOW = 3'd1, RED = 3'd2, WALK = 3'd3, RED_YELLOW = 3'd4;
    reg [2:0] state = RED;
    reg [31:0] timer = 32'd0;               // clocks left in this state
    reg waiting = 1'b0;                     // someone pressed the button
    localparam SEC = 32'd100_000_000;

    reg btn_last = 1'b0;
    always @(posedge clk) begin
        btn_last <= ctrl[0];
        if (ctrl[0] && !btn_last) waiting <= 1'b1;          // remember a press (rising edge)

        if (timer != 32'd0) timer <= timer - 1'b1;
        else case (state)                                   // the timer ran out: where next?
            GREEN:      if (waiting) begin state <= YELLOW; timer <= 2 * SEC; end
            YELLOW:     begin state <= RED; timer <= 1 * SEC; end
            RED:        if (waiting) begin state <= WALK; timer <= 4 * SEC; waiting <= 1'b0; end
                        else begin state <= RED_YELLOW; timer <= 1 * SEC; end
            WALK:       begin state <= RED_YELLOW; timer <= 2 * SEC; end
            RED_YELLOW: begin state <= GREEN; timer <= 3 * SEC; end
            default:    state <= RED;
        endcase
    end

    reg [3:0] lamp;                                         // which lamps each state lights
    always @(*) case (state)
        GREEN:      lamp = 4'b0100;
        YELLOW:     lamp = 4'b0010;
        RED:        lamp = 4'b0001;
        WALK:       lamp = 4'b1001;
        RED_YELLOW: lamp = 4'b0011;
        default:    lamp = 4'b0001;
    endcase
    assign leds = ~lamp;
    assign status = {timer, 28'd0, waiting, state};       // (Python divides by 100 000 000 for seconds)
endmodule
''',
'main.py': r'''# Lesson 5: a state machine. Python watches the traffic light and presses the pedestrian button.
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
CTRL, STATE, LEFT = 0x00, 0x80, 0x84
NAMES = ['GREEN', 'YELLOW', 'RED', 'WALK', 'RED+YELLOW']


def state():
    return regs.read(STATE) & 7


def wait_for(s, timeout):
    t = time.time()
    while state() != s and time.time() - t < timeout:
        time.sleep(0.01)
    return state() == s


check('without a press it settles on GREEN and stays', wait_for(0, 8))
time.sleep(1.5)
check('still GREEN 1.5 s later (nobody pressed)', state() == 0)
regs.write(CTRL, 1); regs.write(CTRL, 0)          # press
seen = []
t = time.time()
while time.time() - t < 12 and (len(seen) < 4):
    s = state()
    if not seen or seen[-1] != s:
        seen.append(s)
    time.sleep(0.02)
check('after a press: GREEN, YELLOW, RED, WALK', seen[:4] == [0, 1, 2, 3], ' -> '.join(NAMES[s] for s in seen))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nThe light runs on its own. Python presses the button every 15 seconds; watch the LEDs.')
last, t_press = None, time.time()
while True:
    s = state()
    if s != last:
        print('%-11s for %.1f s%s' % (NAMES[s], regs.read(LEFT) / 1e8, '  (someone is waiting)' if regs.read(STATE) & 8 else ''), flush=True)
        last = s
    if time.time() - t_press > 15:
        regs.write(CTRL, 1); regs.write(CTRL, 0)
        print('   * button pressed', flush=True)
        t_press = time.time()
    time.sleep(0.05)
''',
}

# ------------------------------------------------------------------------------------------------ 6
LESSONS['learn_06_registers'] = {
'top.v': r'''// Lesson 6: registers on the bus. The ARM and the FPGA talk through memory addresses: writing 0x4120_0000
// changes a register in the FPGA, reading 0x4120_0080 reads a value the FPGA makes. Here: a small calculator.
// The ARM writes A and B, the FPGA answers at once with A+B, A-B, A*B (a hardware multiplier), the larger one,
// A AND B and a count of how many times A was written.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [63:0]  ctrl;                      // ctrl 0 = A (0x4120_0000), ctrl 1 = B (0x4120_0004)
    wire [255:0] status;                    // 8 results at 0x4120_0080 .. 0x4120_009C
    ardzy_soc #(.N_CTRL(2), .N_STAT(8)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    wire [31:0] a = ctrl[31:0];
    wire [31:0] b = ctrl[63:32];
    reg  [63:0] product = 64'd0;            // registered: the multiplier needs a clock
    always @(posedge clk) product <= a * b;

    reg [31:0] writes = 32'd0;              // count changes of A
    reg [31:0] a_last = 32'd0;
    always @(posedge clk) begin
        a_last <= a;
        if (a != a_last) writes <= writes + 1'b1;
    end

    assign status = {32'h4C524547,          // 7: "LREG", the design's name
                     writes,                // 6: how often A changed
                     a & b,                 // 5: bitwise AND
                     (a > b) ? a : b,       // 4: the larger one (unsigned)
                     product[63:32],        // 3: A*B, high 32 bits
                     product[31:0],         // 2: A*B, low 32 bits
                     a - b,                 // 1
                     a + b};                // 0
    assign leds = ~a[3:0];                  // A's lowest 4 bits on the LEDs
endmodule
''',
'main.py': r'''# Lesson 6: registers on the bus. Python writes A and B, the FPGA's answers are read back at once.
import random
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
A, B = 0x00, 0x04
SUM, DIFF, PLO, PHI, MAX, AND, WRITES, NAME = (0x80 + 4 * i for i in range(8))
M = 0xFFFFFFFF

check('the design answers "LREG"', regs.read(NAME) == 0x4C524547, hex(regs.read(NAME)))
random.seed(6)
bad = 0
for _ in range(200):
    a, b = random.getrandbits(32), random.getrandbits(32)
    regs.write(A, a); regs.write(B, b)
    p = regs.read(PLO) | (regs.read(PHI) << 32)
    bad += (regs.read(SUM) != (a + b) & M or regs.read(DIFF) != (a - b) & M or p != a * b
            or regs.read(MAX) != max(a, b) or regs.read(AND) != a & b)
check('200 random A, B: +, -, *, max, AND all right', bad == 0, '%d wrong' % bad)

n = 20000
t = time.time()
for i in range(n):
    regs.read(SUM)
read_us = (time.time() - t) / n * 1e6
t = time.time()
for i in range(n):
    regs.write(A, i)
write_us = (time.time() - t) / n * 1e6
print('A register read takes %.2f us, a write %.2f us (from Python; from C it is about 0.2 us)' % (read_us, write_us))
check('register access works fast (under 20 us from Python)', read_us < 20 and write_us < 20)
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nType two numbers in the Monitor (for example: 1234 5678) and the FPGA calculates.')
while True:
    try:
        a, b = (int(x, 0) for x in input().split()[:2])
    except (ValueError, EOFError):
        print('two numbers please, like: 12 34   or   0x10 7')
        continue
    regs.write(A, a); regs.write(B, b)
    print('A+B = %d   A-B = %d   A*B = %d   max = %d   A AND B = %d' % (
        regs.read(SUM), regs.read(DIFF) - (1 << 32 if regs.read(DIFF) >> 31 else 0),
        regs.read(PLO) | (regs.read(PHI) << 32), regs.read(MAX), regs.read(AND)), flush=True)
''',
}

# ------------------------------------------------------------------------------------------------ 7
LESSONS['learn_07_uart'] = {
'top.v': r'''// Lesson 7: serial data, a UART. One wire carries bytes one bit after the other: a start bit (0), 8 data
// bits (lowest first), a stop bit (1). Both sides agree on the speed (baud rate). Here a transmitter sends what
// the ARM writes, out of J1 pin 11 (TXD), and a receiver reads J1 pin 12 (RXD), or the transmitter itself
// (loopback) when nothing is connected. Received bytes wait in a small FIFO for the ARM.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    output wire       txd,                  // J1 pin 11
    input  wire       rxd                   // J1 pin 12 (pull-up)
);
    wire clk, rstn;
    wire [63:0] ctrl;                       // ctrl 0: [7:0] a byte to send (write = send)   ctrl 1: clocks per bit, [31] loopback
    wire [63:0] status;                     // status 0: [7:0] oldest received byte, [15:8] bytes waiting, [16] sending
    ardzy_soc #(.N_CTRL(2), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));
    wire [15:0] bit_clocks = (ctrl[47:32] < 16'd16) ? 16'd868 : ctrl[47:32];   // 868 = 100 MHz / 115200
    wire loopback = ctrl[63];

    // ---- transmitter: a shift register of 10 bits and a bit timer
    reg [9:0]  tx_shift = 10'h3FF;
    reg [3:0]  tx_left = 4'd0;
    reg [15:0] tx_timer = 16'd0;
    reg [31:0] last_ctrl0 = 32'd0;
    reg [31:0] sent = 32'd0;
    always @(posedge clk) begin
        last_ctrl0 <= ctrl[31:0];
        if (tx_left == 4'd0 && ctrl[31:0] != last_ctrl0) begin      // the ARM wrote a byte
            tx_shift <= {1'b1, ctrl[7:0], 1'b0};                     // stop, data (LSB first), start
            tx_left <= 4'd10;
            tx_timer <= bit_clocks;
        end else if (tx_left != 4'd0) begin
            if (tx_timer == 16'd1) begin
                tx_shift <= {1'b1, tx_shift[9:1]};                   // next bit
                tx_left <= tx_left - 1'b1;
                tx_timer <= bit_clocks;
                if (tx_left == 4'd1) sent <= sent + 1'b1;
            end else tx_timer <= tx_timer - 1'b1;
        end
    end
    assign txd = tx_shift[0];

    // ---- receiver: wait for a start bit, sample each bit in its middle
    wire line = loopback ? txd : rxd;
    reg r1 = 1'b1, r2 = 1'b1;               // synchronizer (lesson 3)
    always @(posedge clk) begin r1 <= line; r2 <= r1; end
    reg [3:0]  rx_n = 4'd0;
    reg [15:0] rx_timer = 16'd0;
    reg [7:0]  rx_byte = 8'd0;
    reg        rx_busy = 1'b0, rx_done = 1'b0;
    always @(posedge clk) begin
        rx_done <= 1'b0;
        if (!rx_busy) begin
            if (!r2) begin rx_busy <= 1'b1; rx_timer <= bit_clocks + (bit_clocks >> 1); rx_n <= 4'd0; end
        end else if (rx_timer != 16'd0) rx_timer <= rx_timer - 1'b1;
        else if (rx_n < 4'd8) begin
            rx_byte <= {r2, rx_byte[7:1]};                           // LSB first
            rx_n <= rx_n + 1'b1;
            rx_timer <= bit_clocks - 1'b1;
        end else begin
            rx_busy <= 1'b0;                                         // (this is the stop bit)
            rx_done <= r2;                                           // a byte only if the stop bit is 1
        end
    end

    // ---- a 16-byte FIFO for the ARM; reading status 0 takes the oldest byte (the ARM writes ctrl 1 [30] to pop)
    reg [7:0] fifo [0:15];
    reg [4:0] wp = 5'd0, rp = 5'd0;
    reg pop_last = 1'b0;
    always @(posedge clk) begin
        pop_last <= ctrl[62];
        if (rx_done && (wp - rp) != 5'd16) begin fifo[wp[3:0]] <= rx_byte; wp <= wp + 1'b1; end
        if (ctrl[62] && !pop_last && wp != rp) rp <= rp + 1'b1;
    end
    wire [4:0] level = wp - rp;
    assign status = {sent, 15'd0, (tx_left != 4'd0), 3'd0, level, (level != 0) ? fifo[rp[3:0]] : 8'd0};
    assign leds = ~{2'b00, rx_busy, tx_left != 4'd0};
endmodule
''',
'main.py': r'''# Lesson 7: a UART. Python sends bytes through the FPGA's transmitter; the FPGA's receiver reads them back.
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
TX, CFG, RX, SENT = 0x00, 0x04, 0x80, 0x84
LOOP, POP = 1 << 31, 1 << 30
BAUD = 115200
cfg = (100_000_000 // BAUD) | LOOP
regs.write(CFG, cfg)
n_written = 0


def send(byte):
    global n_written
    while regs.read(RX) >> 16 & 1:          # wait while the transmitter is busy
        pass
    n_written += 1
    regs.write(TX, (n_written << 8) | byte)  # (the upper bits change at every write, so the same byte twice is sent twice)


def receive(timeout=0.2):
    t = time.time()
    while not (regs.read(RX) >> 8) & 0x1F:
        if time.time() - t > timeout:
            return None
    b = regs.read(RX) & 0xFF
    regs.write(CFG, cfg | POP); regs.write(CFG, cfg)
    return b


def flush():
    """Throw away what the receiver caught before: while it listened to the pin, a low pin looked like a 0 byte."""
    time.sleep(0.01)
    while (regs.read(RX) >> 8) & 0x1F:
        regs.write(CFG, cfg | POP); regs.write(CFG, cfg)


flush()
text = b'Hello, Ardzy!'
got = bytearray()
for ch in text:
    send(ch)
    r = receive()
    if r is not None:
        got.append(r)
print('sent %r, received %r over the internal loopback at %d baud' % (text, bytes(got), BAUD))
check('loopback: every byte comes back', bytes(got) == text)
for baud in (9600, 1_000_000):
    cfg = (100_000_000 // baud) | LOOP
    regs.write(CFG, cfg)
    flush()
    send(0x5A)
    r = receive(0.1)
    check('the same at %d baud' % baud, r == 0x5A, hex(r) if r is not None else 'nothing')
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nNow at 115200 baud on the pins: connect a USB-UART cable (its RX to J1 pin 11, its TX to J1 pin 12,')
print('GND to pin 1) and open the app\'s USB serial tab. Everything you type there comes back in capitals.')
cfg = 100_000_000 // 115200                 # loopback off: the pins
regs.write(CFG, cfg)
for ch in b'Ardzy UART lesson: type something\r\n':
    send(ch)
while True:
    r = receive(1.0)
    if r is not None:
        send(ord(chr(r).upper()))
''',
'pins.xdc': """# Lesson 7: the UART on J1: TXD = pin 11, RXD = pin 12 (with a pull-up)
set_property PACKAGE_PIN T12 [get_ports {txd}]
set_property IOSTANDARD LVCMOS33 [get_ports {txd}]
set_property PACKAGE_PIN U12 [get_ports {rxd}]
set_property IOSTANDARD LVCMOS33 [get_ports {rxd}]
set_property PULLTYPE PULLUP [get_ports {rxd}]
""",
}

# ------------------------------------------------------------------------------------------------ 8
LESSONS['learn_08_memory'] = {
'top.v': r'''// Lesson 8: memory inside the FPGA (block RAM). 1024 words of 32 bits that the ARM writes and the FPGA plays
// back: a light show of up to 1024 steps. Each word: [3:0] the LEDs, [31:8] how many milliseconds to show them.
// A block RAM answers one clock after it is asked (it is synchronous): the design asks one step ahead.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [95:0] ctrl;                       // ctrl 0: [9:0] address  ctrl 1: data (writing it stores data at address)
                                            // ctrl 2: [9:0] number of steps to play, [31] play
    wire [95:0] status;                     // status 0: data read at the address  1: the step now  2: sum of all words
    ardzy_soc #(.N_CTRL(3), .N_STAT(3)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    (* ram_style = "block" *) reg [31:0] mem [0:1023];

    // port A: the ARM writes (when ctrl 1 changes) and reads at its address
    reg [31:0] data_last = 32'd0, rd_a = 32'd0;
    always @(posedge clk) begin
        data_last <= ctrl[63:32];
        if (ctrl[63:32] != data_last) mem[ctrl[9:0]] <= ctrl[63:32];
        rd_a <= mem[ctrl[9:0]];
    end

    // port B: the player while playing; when not playing it reads the memory round and round for a checksum
    reg [9:0]  step = 10'd0, sa = 10'd0;
    reg [31:0] rd_b = 32'd0;
    reg [31:0] ms_left = 32'd0;
    reg [16:0] ms_div = 17'd0;
    reg [3:0]  show = 4'd0;
    reg        loaded = 1'b0, s_valid = 1'b0;
    reg [31:0] sum = 32'd0, sum_done = 32'd0;
    wire       playing = ctrl[95];
    wire [9:0] steps = (ctrl[73:64] == 10'd0) ? 10'd1 : ctrl[73:64];
    always @(posedge clk) begin
        rd_b <= mem[playing ? step : sa];                   // the word asked for, 1 clock later
        ms_div <= (ms_div == 17'd99_999) ? 17'd0 : ms_div + 1'b1;
        if (!playing) begin
            step <= 10'd0; loaded <= 1'b0; ms_left <= 32'd0;
            // checksum: rd_b holds the word at sa - 1; at sa = 0 that is word 1023, the last one of a pass
            sa <= sa + 1'b1;
            s_valid <= 1'b1;
            if (s_valid) begin
                if (sa == 10'd0) begin sum_done <= sum + rd_b; sum <= 32'd0; end
                else sum <= sum + rd_b;
            end
        end else begin
            s_valid <= 1'b0; sa <= 10'd0; sum <= 32'd0;
            if (!loaded) loaded <= 1'b1;                    // wait the 1 clock for rd_b
            else if (ms_left == 32'd0) begin
                show <= rd_b[3:0];
                ms_left <= (rd_b[31:8] == 24'd0) ? 32'd1 : rd_b[31:8];
                step <= (step + 1'b1 >= steps) ? 10'd0 : step + 1'b1;
                loaded <= 1'b0;
            end else if (ms_div == 17'd0) ms_left <= ms_left - 1'b1;
        end
    end
    assign leds = ~show;
    assign status = {sum_done, 22'd0, step, rd_a};
endmodule
''',
'main.py': r'''# Lesson 8: block RAM. Python fills the FPGA's memory with a light show; the FPGA plays it back.
import random
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
ADDR, DATA, PLAY = 0x00, 0x04, 0x08
RDATA, STEP, SUM = 0x80, 0x84, 0x88


def poke(addr, value):
    regs.write(ADDR, addr)
    regs.write(DATA, value ^ 0xFFFFFFFF)     # (a different value first, so the write is seen even if equal)
    regs.write(DATA, value)


def peek(addr):
    regs.write(ADDR, addr)
    return regs.read(RDATA)


random.seed(8)
words = [random.getrandbits(32) for _ in range(1024)]
for a, w in enumerate(words):
    poke(a, w)
bad = sum(peek(a) != w for a, w in enumerate(words))
check('1024 words written and read back', bad == 0, '%d wrong' % bad)
time.sleep(0.01)
check('the FPGA\'s checksum = Python\'s sum', regs.read(SUM) == sum(words) & 0xFFFFFFFF,
      '%08x / %08x' % (regs.read(SUM), sum(words) & 0xFFFFFFFF))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nA light show from memory: a bouncing light, then all LEDs counting in binary.')
show = []
for p in [1, 2, 4, 8, 4, 2] * 3:
    show.append((p, 120))                  # (LEDs, milliseconds)
for n in range(16):
    show.append((n, 200))
for i, (leds, ms) in enumerate(show):
    poke(i, (ms << 8) | leds)
regs.write(PLAY, (1 << 31) | len(show))
print('%d steps playing on their own, the ARM does nothing now. Step number now:' % len(show))
while True:
    print('  step %d' % regs.read(STEP), flush=True)
    time.sleep(1)
''',
}

# ------------------------------------------------------------------------------------------------ 9
LESSONS['learn_09_frequency'] = {
'top.v': r'''// Lesson 9: making and measuring frequencies. A divider makes a square wave on J1 pin 11; a counter at the pin
// itself (the pad, read back through the input buffer) counts its rising edges for exactly 1 second (the gate)
// = the frequency in Hz, and measures one period in clocks (10 ns each) for fine resolution at low frequencies.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds,
    inout  wire       sig                   // J1 pin 11: an output we also read back at the pad
);
    wire clk, rstn;
    wire [31:0] ctrl;                       // ctrl: half period in clocks (frequency = 50 MHz / ctrl)
    wire [95:0] status;                     // 0: edges in the last second (Hz)  1: last period in clocks  2: gates done
    ardzy_soc #(.N_CTRL(1), .N_STAT(3)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    // the generator: toggle every ctrl clocks
    reg [31:0] div = 32'd0;
    reg out = 1'b0;
    wire [31:0] half = (ctrl == 32'd0) ? 32'd50_000 : ctrl;          // default 1 kHz
    always @(posedge clk) begin
        if (div + 1'b1 >= half) begin div <= 32'd0; out <= ~out; end
        else div <= div + 1'b1;
    end
    wire pad;                                            // the pin as its input buffer sees it
    IOBUF iob (.IO(sig), .I(out), .T(1'b0), .O(pad));    // T = 0: always driven, and read back at the pad

    reg p1 = 1'b0, p2 = 1'b0, p3 = 1'b0;                 // synchronizer + edge detector (lessons 3)
    always @(posedge clk) begin p1 <= pad; p2 <= p1; p3 <= p2; end
    wire rise = p2 & ~p3;

    // frequency: count edges during a 1-second gate
    reg [26:0] gate = 27'd0;
    reg [31:0] edges = 32'd0, hz = 32'd0, gates = 32'd0;
    always @(posedge clk) begin
        if (gate == 27'd99_999_999) begin
            gate <= 27'd0; hz <= edges + rise; edges <= 32'd0; gates <= gates + 1'b1;
        end else begin
            gate <= gate + 1'b1;
            if (rise) edges <= edges + 1'b1;
        end
    end
    // period: clocks between two rising edges
    reg [31:0] pc = 32'd0, period = 32'd0;
    always @(posedge clk) begin
        if (rise) begin period <= pc + 1'b1; pc <= 32'd0; end
        else if (pc != 32'hFFFFFFFF) pc <= pc + 1'b1;
    end
    assign status = {gates, period, hz};
    assign leds = ~{3'b000, (hz != 32'd0)};
endmodule
''',
'main.py': r'''# Lesson 9: frequencies. Python asks for a frequency, the FPGA makes it on a pin and measures it at the pin.
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
HALF, HZ, PERIOD, GATES = 0x00, 0x80, 0x84, 0x88


def measure(freq):
    half = max(1, round(50e6 / freq))
    regs.write(HALF, half)
    g = regs.read(GATES)
    while regs.read(GATES) < g + 2:          # wait for a whole gate with the new frequency
        time.sleep(0.05)
    return 50e6 / half, regs.read(HZ), regs.read(PERIOD)


bad = []
for f in (10, 1000, 123456, 5e6):
    want, hz, per = measure(f)
    print('asked %10.1f Hz: made %12.3f Hz, counted %10d Hz in 1 s, one period = %d clocks = %.3f Hz' % (f, want, hz, per, 100e6 / per))
    if abs(hz - want) > max(1, want * 1e-5) or abs(100e6 / per - want) > want * 1e-3:
        bad.append(f)
check('counted and period-measured = made', not bad, 'wrong at %s' % bad if bad else '')
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nWhich is better? At 10 Hz the 1-second count says "10", the period says "10.000": more digits.')
print('At 5 MHz the count has 7 digits, the period only 20 clocks (2 digits). Real counters use both.')
print('The signal stays on J1 pin 11 (1 kHz): look at it with a scope or the Tools logic analyzer later.')
regs.write(HALF, 50000)
while True:
    time.sleep(2)
    print('measuring: %d Hz' % regs.read(HZ), flush=True)
''',
'pins.xdc': """# Lesson 9: the signal on J1 pin 11 (an output read back at the pad)
set_property PACKAGE_PIN T12 [get_ports {sig}]
set_property IOSTANDARD LVCMOS33 [get_ports {sig}]
""",
}

# ------------------------------------------------------------------------------------------------ 10
LESSONS['learn_10_plotter'] = {
'top.v': r'''// Lesson 10: your own instrument. A DDS (direct digital synthesis) oscillator: a 32-bit phase grows by a step
// every clock and its top bits address a sine table (the library's ardzy_sine_rom). The ARM sets the step, reads
// samples and prints them for the app's Plotter. The same idea makes the signal generator of project 06 and the
// FM radio's carrier.
`timescale 1ns / 1ps
module top (
    output wire [3:0] leds
);
    wire clk, rstn;
    wire [63:0] ctrl;                       // ctrl 0: phase step per clock   ctrl 1: [15:0] amplitude, [17:16] wave
    wire [63:0] status;                     // status 0: the wave now (signed 16 bit)   status 1: the phase
    ardzy_soc #(.N_CTRL(2), .N_STAT(2)) soc (.clk(clk), .rstn(rstn), .ctrl(ctrl), .status(status));

    reg [31:0] phase = 32'd0;
    always @(posedge clk) phase <= phase + ctrl[31:0];         // frequency = step / 2^32 x 100 MHz

    wire signed [15:0] sine;
    ardzy_sine_rom rom (.clk(clk), .a(phase[31:22]), .q(sine)); // 1024 points per period

    wire signed [15:0] tri_w = phase[31] ? (16'sd32767 - $signed({1'b0, phase[30:16]}) * 2) : (-16'sd32767 + $signed({1'b0, phase[30:16]}) * 2);
    wire signed [15:0] saw = $signed(phase[31:16]);
    wire signed [15:0] sq  = phase[31] ? -16'sd32767 : 16'sd32767;
    reg  signed [15:0] wave;
    always @(*) case (ctrl[49:48])
        2'd0: wave = sine;
        2'd1: wave = tri_w;
        2'd2: wave = saw;
        default: wave = sq;
    endcase
    wire signed [31:0] scaled = wave * $signed({1'b0, ctrl[47:32]});
    reg signed [15:0] out = 16'sd0;
    always @(posedge clk) out <= scaled >>> 15;
    assign status = {phase, {16{out[15]}}, out};
    assign leds = ~(4'b0001 << phase[31:30]);                    // a light that goes round once per period
endmodule
''',
'main.py': r'''# Lesson 10: your own instrument. Python sets the oscillator, reads it and prints for the Plotter.
# Open the bottom panel's Plotter tab: lines like  wave:123  are drawn as a graph.
import math
import time
from ardzy import MMIO
''' + CHECK_PY + r'''
regs = MMIO(0x41200000)
STEP, AMP, WAVE, PHASE = 0x00, 0x04, 0x80, 0x84


def s16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v


def set_osc(freq, amp=30000, shape=0):
    regs.write(STEP, round(freq / 100e6 * 2 ** 32))
    regs.write(AMP, (shape << 16) | amp)


set_osc(1000)
p0, t0 = regs.read(PHASE), time.time()
time.sleep(0.5)
p1, t1 = regs.read(PHASE), time.time()
cycles = ((p1 - p0) & 0xFFFFFFFF) / 2 ** 32       # (the phase wraps 500 times in 0.5 s at 1 kHz; this counts within one)
set_osc(0.5)                                         # slow: 0.5 Hz
peak = 0
t = time.time()
while time.time() - t < 2.2:
    peak = max(peak, abs(s16(regs.read(WAVE))))
check('a 0.5 Hz sine reaches its amplitude (30000)', abs(peak - 30000) < 300, 'peak %d' % peak)
set_osc(0.5, 30000, 3)
v = set()
t = time.time()
while time.time() - t < 2.2:                         # a whole period (about 2 s)
    v.add(s16(regs.read(WAVE)))
check('the square wave has 2 levels, +30000 and -30000', len(v) == 2 and all(abs(abs(x) - 30000) < 5 for x in v), str(sorted(v)))
print('RESULT: %d of %d ok' % (sum(results), len(results)), flush=True)

print('\nOpen the Plotter tab. Every 4 seconds the shape changes: sine, triangle, sawtooth, square.')
shapes = ['sine', 'triangle', 'sawtooth', 'square']
n = 0
while True:
    set_osc(0.5, 30000, n % 4)
    print('now: %s' % shapes[n % 4], flush=True)
    t = time.time()
    while time.time() - t < 4:
        print('wave:%d' % s16(regs.read(WAVE)), flush=True)
        time.sleep(0.04)
    n += 1
''',
}


def main():
    for name, files in LESSONS.items():
        d = os.path.join(TPL, name)
        os.makedirs(d, exist_ok=True)
        changed = []
        for f, text in list(files.items()) + [('leds.xdc', LEDS_XDC)]:
            path = os.path.join(d, f)
            old = open(path, encoding='utf-8').read() if os.path.isfile(path) else None
            if old != text:                  # (unchanged files keep their time: the prebuilt .bit stays newer)
                open(path, 'w', encoding='utf-8', newline='\n').write(text)
                changed.append(f)
        print('%-20s %s' % (name, ', '.join(changed) if changed else 'unchanged'))
        if any(f.endswith(('.v', '.xdc')) for f in changed):
            print('    the design changed: build it again (tests/learn_lessons_test.py does)')


if __name__ == '__main__':
    main()
