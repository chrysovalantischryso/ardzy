/* Ardzy - Learn: the course content. Each lesson: what you will learn, the idea explained with an interactive
   widget, the lesson's real project (pc_app/templates/learn_NN_*: created and uploaded with one click), the code,
   a quiz with explanations and challenges with hints and answers. learn.js shows it. */
const LEARN = {
  intro: `<p>An FPGA is a chip full of tiny logic blocks and wires that <b>you</b> connect: you do not write a program
    that runs step by step, you describe <b>hardware</b> that does everything at the same time. The Ardzy board has one
    (the Zynq's FPGA part) right next to two ARM processors running Linux, so you can build hardware and talk to it from
    Python in the same minute.</p>
    <p>Each lesson has a working project. Press <b>Create the project</b>, then <b>Upload and run</b>: the program first
    checks the hardware (the lines starting with CHECK in the Monitor) and then runs a demo you can change. Read the
    code, change one thing, upload again. That is how everybody learns this.</p>`,
  lessons: [
  {
    id: 1, template: 'learn_01_logic', minutes: 20, need: 'nothing',
    title: 'Logic gates: what an FPGA is made of',
    goal: 'Know what AND, OR, XOR and NOT do, what a LUT is, and write your first hardware in Verilog.',
    sections: [
      { h: 'Everything is 0 and 1', html: `<p>Inside a chip a wire is either low (0, about 0 V) or high (1, here 3.3 V or 1 V inside
        the chip). A <b>logic gate</b> looks at its inputs and sets its output: AND is 1 only when all its inputs are 1, OR when
        any input is 1, XOR when the inputs are different, NOT turns 1 into 0 and 0 into 1. With enough gates you can build
        anything digital: adders, memories, whole processors.</p>` },
      { widget: 'gates' },
      { h: 'An FPGA has no gates: it has LUTs', html: `<p>An FPGA does not contain AND or OR gates. It contains thousands of
        <b>LUTs</b> (look-up tables): tiny memories with 6 address inputs and 1 output. A LUT can be <i>any</i> function of its
        inputs: the build tools simply write the truth table into it. The XC7Z010 on this board has 17 600 of them, plus
        35 200 flip-flops (lesson 2), 60 block RAMs (lesson 8) and 80 multipliers.</p>
        <p>Click the outputs in the LUT above: you are programming a LUT, exactly what the tools do with your Verilog.</p>` },
      { h: 'Verilog in four lines', html: `<p><code>wire f_and = a &amp; b;</code> describes a wire whose value is a AND b, all the
        time. It is not an instruction executed once: it is a connection that exists as long as the design is loaded.
        <code>|</code> is OR, <code>^</code> is XOR, <code>~</code> is NOT. The lesson's design reads a, b and c from a register
        the ARM writes (<code>ctrl</code>) and sends the four answers to the LEDs and back to the ARM (<code>status</code>).</p>` },
    ],
    files: ['top.v', 'main.py'],
    steps: ['Press <b>Create the project</b> (it appears in Code, with a prebuilt FPGA design).',
      'Press <b>Upload and run</b>. The Monitor prints the truth table the FPGA computed and CHECK ok.',
      'Watch the LEDs: they show AND, OR, XOR and MAJ while the inputs count from 0 to 7.',
      'Change a function in <code>top.v</code> (for example <code>f_and = ~(a &amp; b)</code>, a NAND), press <b>Build FPGA</b> (about a minute), then Upload again.'],
    quiz: [
      { q: 'a = 1, b = 0. What is a XOR b?', options: ['0', '1'], answer: 1, why: 'XOR is 1 when its inputs are different.' },
      { q: 'What is inside an FPGA instead of fixed gates?', options: ['Small processors', 'LUTs: tiny programmable truth tables', 'Transistors you solder'], answer: 1,
        why: 'A LUT stores the truth table of any function of its inputs; the tools fill it from your Verilog.' },
      { q: 'When does <code>wire f = a &amp; b;</code> compute its value?', options: ['Once, when the line runs', 'All the time: it is a wire', 'When the ARM asks'], answer: 1,
        why: 'Verilog describes hardware. The AND gate is always there and its output follows the inputs within nanoseconds.' },
    ],
    challenges: [
      { task: 'Make LED 3 show "all three inputs are 1".', hint: 'AND can take more than two inputs.', answer: '<code>wire f_maj = a &amp; b &amp; c;</code>' },
      { task: 'Make a 1-bit adder: LED 0 = the sum bit of a + b, LED 1 = the carry.', hint: '1 + 1 = 10 in binary: sum 0, carry 1.', answer: 'sum = <code>a ^ b</code>, carry = <code>a &amp; b</code>. That is a half adder; two of them and an OR make a full adder.' },
      { task: 'How many different functions can one 6-input LUT be?', hint: 'A truth table with 6 inputs has 2^6 rows, each row 0 or 1.', answer: '2^64, about 18 billion billion: every possible function of 6 inputs.' },
    ],
  },
  {
    id: 2, template: 'learn_02_counter', minutes: 20, need: 'nothing',
    title: 'The clock and a counter: hardware that remembers',
    goal: 'Understand clocks, flip-flops and registers, and make LEDs blink by counting 100 million times a second.',
    sections: [
      { h: 'The clock', html: `<p>Gates answer at once, but they cannot <b>remember</b>. For that the FPGA has flip-flops:
        each stores one bit and changes it only at the <b>rising edge</b> of a clock, a signal that goes 0, 1, 0, 1 at a
        steady rate. Here the clock is 100 MHz: 100 million edges per second, one every 10 nanoseconds.</p>
        <p>A group of flip-flops is a <b>register</b>. <code>always @(posedge clk) count &lt;= count + 1;</code> means: at every
        rising edge, the register count takes the value count + 1. An adder made of LUTs computes count + 1 all the time;
        the flip-flops take the answer at the edge.</p>` },
      { widget: 'counter' },
      { h: 'Dividing by two, again and again', html: `<p>Bit 0 of a counter changes at every clock: 50 MHz. Bit 1 changes half as
        often: 25 MHz. Bit n toggles at 100 MHz / 2^(n+1). To see an LED blink about once a second you need a bit around 26:
        100 000 000 / 2^27 = 0.75 blinks per second. That is the oldest trick in digital design: a counter is a frequency divider.</p>` },
      { h: 'Software measures hardware', html: `<p>The lesson's <code>main.py</code> reads the counter, waits one second, reads it
        again: the difference is about 100 000 000. Python is slow and its timing wobbles by microseconds, but the counter is
        exact: the hardware keeps time, the software just looks at it.</p>` },
    ],
    files: ['top.v', 'main.py'],
    steps: ['<b>Create the project</b>, then <b>Upload and run</b>.', 'The Monitor shows the measured counting rate (about 100 MHz) and CHECK ok.',
      'The LEDs show four bits of the counter; main.py moves the window from fast bits to slow ones.',
      'In <code>main.py</code> change <code>regs.write(CTRL, 23)</code> to 22: the counter on the LEDs runs twice as fast.'],
    quiz: [
      { q: 'A flip-flop changes its value ...', options: ['whenever its input changes', 'only at the clock edge', 'when the ARM writes it'], answer: 1,
        why: 'That is the whole point: everything in the design changes together, in step with the clock.' },
      { q: 'At 100 MHz, how fast does bit 3 of a counter toggle?', options: ['100 MHz / 8 = 12.5 MHz', '100 MHz / 16 = 6.25 MHz', '100 MHz / 3'], answer: 1,
        why: 'Bit n completes a cycle every 2^(n+1) clocks: 2^4 = 16.' },
      { q: 'Why does main.py measure about 100 000 000 per second, not exactly?', options: ['The FPGA clock is unstable', 'Python\'s own timing (sleep, reading the time) wobbles a little', 'The counter skips values'], answer: 1,
        why: 'The FPGA counts every edge; the uncertainty is in when Python reads the counter.' },
    ],
    challenges: [
      { task: 'Make the counter count down instead of up.', hint: 'Change one character in top.v.', answer: '<code>count &lt;= count - 1\'b1;</code> The LEDs then show the bits inverted in time.' },
      { task: 'Make a counter that counts only to 9 and starts again at 0 (a decade counter).', hint: 'An if inside the always block.', answer: '<code>if (count == 9) count &lt;= 0; else count &lt;= count + 1;</code> This divides by 10 instead of by a power of 2.' },
      { task: 'How many bits does a counter need to count one whole day at 100 MHz without overflowing?', hint: '100e6 x 86400 = 8.64e12.', answer: '2^43 = 8.8e12, so 43 bits. A 32-bit counter overflows after 43 seconds.' },
    ],
  },
  {
    id: 3, template: 'learn_03_edges', minutes: 25, need: 'optional: a button and two wires',
    title: 'Edges, synchronizers and debouncing: reading the real world',
    goal: 'Detect the moment something changes, bring outside signals safely into the clock domain, and clean up a bouncing button.',
    sections: [
      { h: 'An edge is a change', html: `<p>Often you care not that a button <i>is</i> pressed but that it <i>was just</i> pressed.
        Keep last clock's value in a flip-flop and compare: <code>press = now &amp; ~before;</code> is 1 for exactly one clock
        when the signal goes from 0 to 1. That is a <b>rising-edge detector</b>, used everywhere.</p>` },
      { widget: 'timing' },
      { h: 'The outside world has no clock', html: `<p>A button can change at any moment, even during the tiny window in which a
        flip-flop is taking its value. The flip-flop can then hang half way for a while (<b>metastability</b>). The cure: two
        flip-flops in a row (a <b>synchronizer</b>). The first may wobble; it has a whole clock to settle before the second
        takes it. Every signal from outside the clock domain needs one.</p>` },
      { h: 'Buttons bounce', html: `<p>A mechanical contact does not close cleanly: it bounces open and closed for one to five
        milliseconds. At 100 MHz that is hundreds of thousands of clocks, so a naive counter would count dozens of presses. A
        <b>debouncer</b> accepts a new level only after it has been steady for 5 ms. The lesson counts both: the raw changes
        (bounces) and the clean presses.</p>` },
    ],
    files: ['top.v', 'main.py', 'pins.xdc'],
    steps: ['<b>Create the project</b> and <b>Upload and run</b>. Python "presses" a virtual button, also with bounces: CHECK ok twice.',
      'Optional: a push button between J1 pin 5 and GND (pin 1). Each press toggles LED 0; the Monitor shows the raw changes it saw.',
      'Try: in top.v change 499_999 to 99 (1 microsecond of debouncing), build, upload, press the real button: it counts bounces as presses.'],
    quiz: [
      { q: '<code>press = now &amp; ~before</code> is 1 ...', options: ['while the button is held', 'for one clock when the button goes down', 'when the button is released'], answer: 1,
        why: 'Only in the clock where now is already 1 and before is still 0.' },
      { q: 'Why two flip-flops in a synchronizer?', options: ['To delay the signal', 'To give a possibly undecided first flip-flop a clock to settle', 'Two are faster than one'], answer: 1,
        why: 'Metastability resolves quickly but not instantly; the second flip-flop sees a settled value.' },
      { q: 'A button bounces for 3 ms. Is a 5 ms debounce enough?', options: ['Yes', 'No'], answer: 0,
        why: 'The level must be steady for 5 ms before it is accepted; 3 ms of bounces are swallowed.' },
    ],
    challenges: [
      { task: 'Count releases instead of presses.', hint: 'A falling edge: now 0, before 1.', answer: '<code>wire release = ~clean &amp; clean_last;</code>' },
      { task: 'Make a long press (over 1 second) light LED 2.', hint: 'Count clocks while clean is 1.', answer: 'A 27-bit counter that runs while <code>clean</code> is 1 and resets when 0; LED 2 = counter &gt;= 100_000_000.' },
      { task: 'Why must the debounce counter reset when the input matches the clean level again?', hint: 'Think of a bounce in the middle of the wait.', answer: 'Otherwise a bounce back would not restart the 5 ms: the level must be steady for the whole time.' },
    ],
  },
  {
    id: 4, template: 'learn_04_pwm', minutes: 20, need: 'nothing (optional: a scope or LED on J1 pin 11)',
    title: 'PWM: brightness and power from fast switching',
    goal: 'Make "analog" brightness from a digital pin and measure a duty cycle in hardware.',
    sections: [
      { h: 'On, off, and the average', html: `<p>A pin is 0 or 1, nothing between. But switch it on for 25 % of the time and off for
        75 %, fast enough, and an LED looks a quarter bright, a motor runs at a quarter speed, a heater heats a quarter. That is
        <b>PWM</b> (pulse width modulation). The share of on-time is the <b>duty cycle</b>.</p>` },
      { widget: 'pwm' },
      { h: 'How the hardware does it', html: `<p>A counter runs 0, 1, ... 255, 0, ... and the output is 1 while the counter is below
        the brightness value. Brightness 64 gives 64 of 256 steps on: 25 %. One comparator per LED, all four running at the same
        time from the same counter. At 100 MHz / 16 / 256 the PWM runs at 24 kHz: far too fast to flicker.</p>
        <p>Your eye is not linear: half the light does not look half as bright. The demo squares the sine to make the breathing
        look even (a simple <b>gamma</b> correction).</p>` },
    ],
    files: ['top.v', 'main.py', 'pins.xdc'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>: the FPGA measures its own duty at five levels (CHECK ok).',
      'Then the four LEDs breathe one after another.', 'Change the 3 in <code>t / 3</code> in main.py to 1: they breathe three times faster.'],
    quiz: [
      { q: 'Brightness 192 of 256 is a duty cycle of ...', options: ['192 %', '75 %', '25 %'], answer: 1, why: '192 / 256 = 0.75.' },
      { q: 'Why 24 kHz and not 24 Hz?', options: ['At 24 Hz you would see flicker', 'Faster uses less power', 'The LED needs it'], answer: 0,
        why: 'The eye integrates fast switching; below about 100 Hz you see blinking.' },
      { q: 'How many PWM channels could the FPGA run at once?', options: ['4, one per LED', 'As many as there are pins and LUTs', 'One'], answer: 1,
        why: 'Each channel is just a comparator; they all run in parallel. Microcontrollers have a fixed number of PWM units.' },
    ],
    challenges: [
      { task: 'Make the PWM 10 bits (0 to 1023) for finer steps.', hint: 'A wider ramp and wider brightness fields.', answer: 'ramp <code>[9:0]</code>, compare with 10 bits of ctrl; at the same speed the PWM frequency drops 4 times.' },
      { task: 'Drive a hobby servo: 50 Hz, a pulse of 1 to 2 ms.', hint: '100 MHz / 50 = 2 000 000 clocks per period.', answer: 'A counter to 1 999 999; output high while the counter is below 100 000 .. 200 000 (1 .. 2 ms). Project 04 and the I/O view do this for you.' },
      { task: 'Why does the measured duty for 255 read 99.6 % and not 100 %?', hint: 'ramp &lt; 255 is false when ramp = 255.', answer: 'With 8 bits the output is on for at most 255 of 256 steps. Use 9-bit brightness or treat 255 as "always on".' },
    ],
  },
  {
    id: 5, template: 'learn_05_fsm', minutes: 25, need: 'nothing',
    title: 'State machines: a traffic light',
    goal: 'Design behaviour as states and transitions: the most common structure in digital design.',
    sections: [
      { h: 'States and transitions', html: `<p>A traffic light is always in one <b>state</b> (green, yellow, red ...). Something makes
        it move to the next: a timer running out, a button. Drawn as circles and arrows, that is a <b>finite state machine</b>
        (FSM). In hardware: a small register holds the state, and at every clock edge a <code>case</code> decides the next one.</p>` },
      { widget: 'fsm' },
      { h: 'Reading the code', html: `<p><code>case (state)</code> lists every state; inside, <code>if (waiting)</code> and the timer decide
        where to go and for how long. A second, separate <code>case</code> decides what the lamps show in each state. Keeping
        "where next" and "what to show" apart is good style: each part stays small and easy to check.</p>` },
    ],
    files: ['top.v', 'main.py'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>: Python checks the order of the states after a button press.',
      'LED 0 red, LED 1 yellow, LED 2 green, LED 3 walk. Python presses the button every 15 seconds.',
      'Change <code>timer &lt;= 3 * SEC</code> for RED_YELLOW to 1, build, upload: the light gets impatient.'],
    quiz: [
      { q: 'What makes the light leave GREEN?', options: ['The timer alone', 'A press (waiting) after the timer ran out', 'Nothing'], answer: 1,
        why: 'GREEN stays as long as nobody waits; that is why it settles there.' },
      { q: 'How many flip-flops hold 5 states?', options: ['5', '3', '1'], answer: 1, why: '3 bits can number 8 states.' },
      { q: 'Why is <code>waiting</code> set on the edge of the button and not its level?', options: ['A long press would count many times', 'It saves a flip-flop', 'It is faster'], answer: 0,
        why: 'Lesson 3: an edge happens once per press.' },
    ],
    challenges: [
      { task: 'Add a night mode: when ctrl[1] is 1, blink yellow once a second.', hint: 'A new state, entered from any state when ctrl[1] is 1.', answer: 'State NIGHT with lamp = yellow when a 1-second counter bit is 1; leave to RED when ctrl[1] goes 0.' },
      { task: 'Draw the state diagram on paper for the lesson design.', hint: 'Five circles, arrows with their conditions.', answer: 'GREEN -(press, timer 0)-> YELLOW -> RED -(waiting)-> WALK -> RED_YELLOW -> GREEN; RED -(no one)-> RED_YELLOW.' },
      { task: 'What happens if two people press during WALK?', hint: 'Where is waiting cleared?', answer: 'waiting is cleared on entering WALK and set again by the presses: the next cycle gives them their own WALK.' },
    ],
  },
  {
    id: 6, template: 'learn_06_registers', minutes: 20, need: 'nothing',
    title: 'Registers on the bus: how software talks to hardware',
    goal: 'Understand memory-mapped registers, addresses, and how fast the ARM can reach the FPGA.',
    sections: [
      { h: 'Addresses', html: `<p>To the ARM, the FPGA looks like memory. Writing the address <code>0x4120_0000</code> does not store
        anything in RAM: the bus (AXI) carries the write into the FPGA, where it lands in a register of your design. Reading
        <code>0x4120_0080</code> asks the FPGA for a value. This is <b>memory-mapped I/O</b>, how every peripheral of every
        processor works: UARTs, timers, graphics cards.</p>` },
      { widget: 'regmap' },
      { h: 'Hardware answers at once', html: `<p>The lesson's design adds, subtracts and multiplies A and B continuously. The moment
        Python writes A, the answers change, and the next read sees them. The multiplier uses one of the chip's 80 DSP blocks:
        a 32 x 32 bit product in one clock.</p>
        <p>Every access crosses the bus: from Python it takes a few microseconds (Python itself is the slow part), from C about
        0.2 us. For millions of operations per second, the FPGA must work on its own (lessons 8 and 10).</p>` },
    ],
    files: ['top.v', 'main.py'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>: 200 random pairs checked, and the time per register access.',
      'Type two numbers in the Monitor input line (for example <code>1234 5678</code>) and press Enter.',
      'Add a result: <code>a / b</code> is expensive in hardware; try <code>a &lt;&lt; b[4:0]</code> (shift) in status slot 7.'],
    quiz: [
      { q: 'What is at 0x4120_0080 in this design?', options: ['RAM', 'The first value the FPGA makes (A + B)', 'The Linux kernel'], answer: 1,
        why: 'ardzy_soc maps ctrl registers from 0x4120_0000 and status registers from 0x4120_0080.' },
      { q: 'Why is the product registered (<code>always @(posedge clk) product &lt;= a * b</code>)?', options: ['A multiplier is slow: the register gives it a full clock', 'To save power', 'Verilog needs it'], answer: 0,
        why: 'A 32 x 32 multiply takes several ns; registering it keeps the path inside one clock.' },
      { q: 'Python reads a register in about 2 us. How many reads per second?', options: ['About 500 000', 'About 100 million', 'About 1000'], answer: 0,
        why: '1 / 2 us = 500 000. The FPGA does 100 million things per second: let it do the work.' },
    ],
    challenges: [
      { task: 'Write the same test in C (New project, template "C program") and compare the speed.', hint: 'main.c maps the FPGA with mmap of /dev/mem; map 0x41200000 the same way.', answer: 'r = mmap(..., 0x41200000); r[0] = a; r[1] = b; sum = r[32]; (0x80 / 4 = 32). Expect C to be many times faster than Python.' },
      { task: 'Count how often B changes, like A.', hint: 'Copy the a_last logic.', answer: 'b_last register, writes_b counter, put it into a status slot.' },
      { task: 'Why does reading a register that does not exist return 0 instead of crashing?', hint: 'Look at the comment in ardzy_soc.v.', answer: 'The library answers every address in its window; a missing answer would hang the bus and the whole ARM.' },
    ],
  },
  {
    id: 7, template: 'learn_07_uart', minutes: 30, need: 'optional: a USB-UART cable (3.3 V)',
    title: 'Serial data: build a UART',
    goal: 'Send bytes one bit at a time with exact timing, and receive them back: shift registers and bit timing.',
    sections: [
      { h: 'One wire, one bit at a time', html: `<p>A UART sends a byte as a <b>frame</b>: the line rests at 1; a <b>start bit</b> (0)
        says "here it comes", then 8 data bits, the lowest first, then a <b>stop bit</b> (1). Both ends agree on the speed: at
        115200 baud a bit lasts 8.68 us, 868 clocks at 100 MHz. There is no clock wire: the receiver starts its own timer at the
        start bit and samples each bit in its middle.</p>` },
      { widget: 'uart' },
      { h: 'Shift registers', html: `<p>The transmitter loads the 10 bits of the frame into a register and shifts it one place to the
        right every 868 clocks; the lowest bit is the pin. The receiver does the opposite: every bit time it shifts the pin's value
        in from the left. After 8 shifts the byte is complete. A shift register turns parallel data into serial and back: the
        heart of SPI, I2C, USB, Ethernet and HDMI.</p>` },
    ],
    files: ['top.v', 'main.py', 'pins.xdc'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>: "Hello, Ardzy!" goes through the internal loopback at three speeds.',
      'Optional: a 3.3 V USB-UART cable: its RX to J1 pin 11, its TX to J1 pin 12, GND to pin 1. Open the USB serial tab at 115200: type, and the FPGA echoes in capitals.',
      'Try other speeds in main.py; the hardware takes anything from 16 clocks per bit (6 Mbaud).'],
    quiz: [
      { q: 'How many bits does a UART send for one byte?', options: ['8', '10', '9'], answer: 1, why: 'Start + 8 data + stop.' },
      { q: 'Why does the receiver wait 1.5 bit times after the start edge?', options: ['To land in the middle of data bit 0', 'To skip the stop bit', 'For safety'], answer: 0,
        why: '1 bit time for the start bit, half a bit to reach the middle of bit 0, where the level is most stable.' },
      { q: 'The letter A is 0x41 = 0100 0001. Which data bit is sent first?', options: ['0', '1'], answer: 1, why: 'Lowest bit first: bit 0 of 0x41 is 1.' },
    ],
    challenges: [
      { task: 'Add a parity bit (even parity) to the transmitter.', hint: '^byte is the XOR of all bits.', answer: 'An 11-bit frame: {1, ^byte, byte, 0}, and the receiver checks it.' },
      { task: 'At 1 Mbaud, how many bytes per second at most?', hint: '10 bits per byte.', answer: '100 000 bytes per second.' },
      { task: 'What goes wrong if the two ends differ in speed by 5 %?', hint: 'Count how far the sampling point drifts over 10 bits.', answer: 'After 9.5 bits the sample is 0.475 bit late: almost at the edge. UARTs need the speeds within about 2 to 3 %.' },
    ],
  },
  {
    id: 8, template: 'learn_08_memory', minutes: 25, need: 'nothing',
    title: 'Memory: block RAM',
    goal: 'Use the FPGA\'s block RAM, understand its one-clock read and dual ports, and let hardware play data on its own.',
    sections: [
      { h: 'Block RAM', html: `<p>Registers made of flip-flops are fast but few. For more data the FPGA has <b>block RAMs</b>: 60
        blocks of 36 kbit each in this chip. A block RAM is <b>synchronous</b>: you give it an address at one clock edge and the
        data appears at the next. Each has <b>two ports</b>, two independent address-data pairs that work at the same time.</p>` },
      { widget: 'memory' },
      { h: 'Two ports, two jobs', html: `<p>In the lesson, port A belongs to the ARM (write a word, read a word). Port B belongs to a
        player that walks through a light show stored in the memory, step by step, with the timing stored next to the LED
        pattern. Once loaded, the ARM can do nothing at all and the show runs on its own. When the player is stopped, port B adds
        up the whole memory for a checksum.</p>` },
    ],
    files: ['top.v', 'main.py'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>: 1024 random words written, read back and summed by the FPGA.',
      'Then a light show plays from memory. Change the patterns and times in main.py.'],
    quiz: [
      { q: 'You give a block RAM an address at clock 10. When is the data there?', options: ['At clock 10', 'At clock 11', 'Whenever it is ready'], answer: 1,
        why: 'Block RAM reads are registered: one clock later.' },
      { q: 'How many separate addresses can one block RAM use at the same time?', options: ['1', '2', '1024'], answer: 1, why: 'Two ports.' },
      { q: 'Why does the player wait one clock (loaded) after changing step?', options: ['For the RAM to deliver the new word', 'To slow the show', 'To save power'], answer: 0,
        why: 'Ask, then use the answer one clock later: the basic rhythm of every synchronous memory.' },
    ],
    challenges: [
      { task: 'Make the show play backwards.', hint: 'step - 1, and wrap from 0 to steps - 1.', answer: 'step &lt;= (step == 0) ? steps - 1 : step - 1;' },
      { task: 'How many 32-bit words fit into all 60 block RAMs?', hint: '36 kbit each, but usable as 32 bits wide: 1024 words per 36 kbit.', answer: '60 x 1024 = 61 440 words, 240 KB.' },
      { task: 'Store a 64-step melody and play it on a pin as tones (like project 06).', hint: 'Each word: a half period in clocks and a duration.', answer: 'Use the word\'s bits for the tone and the ms counter for the duration, and toggle a pin every "half period" clocks.' },
    ],
  },
  {
    id: 9, template: 'learn_09_frequency', minutes: 25, need: 'nothing (optional: scope or the Tools logic analyzer)',
    title: 'Making and measuring frequencies',
    goal: 'Generate any frequency with a divider and measure frequency two ways: counting in a gate and timing one period.',
    sections: [
      { h: 'Two ways to measure', html: `<p><b>Count</b>: open a gate for exactly one second (100 000 000 clocks) and count the rising
        edges: the count is the frequency in Hz, to 1 Hz. <b>Time</b>: count clocks between two rising edges: the period in
        10 ns steps; frequency = 100 MHz / clocks. Counting is best for fast signals, timing for slow ones.</p>` },
      { widget: 'freq' },
      { h: 'Reading the real pin', html: `<p>The design drives J1 pin 11 and reads the same pin back through its input buffer
        (<code>IOBUF</code>): it measures what really is on the pin, not just its own idea of it. Short the pin to ground with a
        wire and the measurement drops to 0 Hz: proof it is the pin.</p>` },
    ],
    files: ['top.v', 'main.py', 'pins.xdc'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>: 10 Hz, 1 kHz, 123 456 Hz and 5 MHz, made and measured both ways.',
      'Compare the digits of both methods at 10 Hz and at 5 MHz in the Monitor.',
      'Later: load the pin-control design and look at J1 pin 11 with the Tools logic analyzer.'],
    quiz: [
      { q: 'A 1-second gate counts 12 345 edges. The frequency is ...', options: ['12 345 Hz', '12.345 Hz', 'unknown'], answer: 0, why: 'Edges per second = Hz.' },
      { q: 'One period lasts 400 clocks at 100 MHz. The frequency is ...', options: ['400 Hz', '250 kHz', '25 kHz'], answer: 1, why: '100 000 000 / 400 = 250 000.' },
      { q: 'Which method gives more digits for a 5 Hz signal?', options: ['Counting for 1 s', 'Timing a period'], answer: 1,
        why: 'Counting gives "5"; timing gives 20 000 000 clocks: 5.0000000 Hz.' },
    ],
    challenges: [
      { task: 'Make a 0.1 s gate for faster updates.', hint: '10 000 000 clocks; the count is then Hz / 10.', answer: 'gate up to 9_999_999 and multiply the count by 10 (in Python) for Hz.' },
      { task: 'Measure the duty cycle too.', hint: 'Count clocks while high during the period.', answer: 'A second counter for high time between rising edges: duty = high / period.' },
      { task: 'Why is the generated frequency 50 MHz / half, not 100 MHz / half?', hint: 'The output toggles every half clocks.', answer: 'A full period needs two toggles: 2 x half clocks.' },
    ],
  },
  {
    id: 10, template: 'learn_10_plotter', minutes: 25, need: 'nothing',
    title: 'Your own instrument: DDS, sine tables and the Plotter',
    goal: 'Generate waveforms with direct digital synthesis and watch hardware values live in the app\'s Plotter.',
    sections: [
      { h: 'A phase that goes round', html: `<p>DDS (direct digital synthesis) is how function generators, radios and synthesizers make
        precise frequencies. A 32-bit <b>phase</b> register grows by a <b>step</b> every clock and wraps around: one wrap is one
        period. The frequency is step / 2^32 x 100 MHz, adjustable in steps of 0.023 Hz. The top 10 bits of the phase address a
        table of 1024 sine values: the output is a sine at exactly that frequency.</p>` },
      { widget: 'dds' },
      { h: 'Watch it live', html: `<p>Any program line like <code>wave:123</code> in the Monitor is drawn by the <b>Plotter</b> tab (several
        names make several lines). The lesson reads the wave 25 times a second at 0.5 Hz and switches the shape every 4 seconds:
        sine, triangle, sawtooth, square. The same phase gives all four: the triangle and sawtooth are just the phase bits,
        the square is its top bit.</p>` },
    ],
    files: ['top.v', 'main.py'],
    steps: ['<b>Create the project</b>, <b>Upload and run</b>, then open the <b>Plotter</b> tab.',
      'Watch the four shapes. In main.py change <code>set_osc(0.5, ...)</code> to 0.2 for slower waves.',
      'Next: project 06 (signal generator) outputs this to a pin at audio and radio frequencies.'],
    quiz: [
      { q: 'step = 2^32 / 100. What frequency at 100 MHz?', options: ['1 MHz', '100 Hz', '1 Hz'], answer: 0, why: 'step / 2^32 x 100 MHz = 100 MHz / 100.' },
      { q: 'Why use only the top 10 bits of the phase for the table?', options: ['The table has 1024 entries', 'To be faster', 'The low bits are noise'], answer: 0,
        why: 'The low bits still matter: they keep the fine frequency resolution as they carry into the top bits.' },
      { q: 'The square wave is ...', options: ['the top phase bit', 'a separate oscillator', 'the sine rounded'], answer: 0, why: 'The top bit is 0 for half the period and 1 for the other half.' },
    ],
    challenges: [
      { task: 'Add a fifth shape: a pulse 10 % wide.', hint: 'Compare the phase with 10 % of 2^32.', answer: 'wave = (phase &lt; 32\'d429_496_730) ? 32767 : -32767;' },
      { task: 'Make two oscillators and add them (a chord).', hint: 'Two phases, two steps, add the two waves and halve.', answer: 'Two phase registers and two ROM reads (or one ROM used on alternate clocks); out = (sine1 + sine2) / 2.' },
      { task: 'What is the lowest frequency the DDS can make?', hint: 'step = 1.', answer: '100 MHz / 2^32 = 0.023 Hz: one period in 43 seconds.' },
    ],
  },
  ],
};

/* Ideas: what to build next (difficulty 1 easy .. 3 hard), what it teaches and where to start. */
const IDEAS = [
  { t: 'Reaction game', d: 1, cat: 'Games', parts: '2 buttons', learn: 'edges, counters, random numbers', start: 'lesson 3 + 2',
    how: 'An LED lights after a random time; the FPGA measures the reaction to the microsecond, Python keeps the high score.' },
  { t: 'Binary clock', d: 1, cat: 'Display', parts: 'nothing (4 LEDs) or a WS2812 strip', learn: 'counters, dividers', start: 'lesson 2, project 01',
    how: 'Seconds, minutes, hours as counters; show them in binary on LEDs or as colours on a strip.' },
  { t: 'Morse beacon', d: 1, cat: 'Radio', parts: 'nothing', learn: 'state machines, memory', start: 'lesson 5, project 12 (CW mode)',
    how: 'Store a message in block RAM as dots and dashes and key an LED, a pin or the radio carrier.' },
  { t: 'Servo sweeper', d: 1, cat: 'Motion', parts: 'a hobby servo, 5 V supply', learn: 'PWM timing', start: 'lesson 4, I/O view',
    how: '50 Hz pulses of 1 to 2 ms; sweep with a slow counter or from Python.' },
  { t: 'Digital thermometer graph', d: 1, cat: 'Sensors', parts: 'nothing (the chip has one)', learn: 'the XADC, Python, the Plotter', start: 'Board view, Plotter',
    how: 'Read the chip temperature every second and print temp:52.3 lines; heat the chip with project 13 mining and watch.' },
  { t: 'Frequency counter with display', d: 2, cat: 'Instruments', parts: 'MAX7219 8-digit display (SPI)', learn: 'gates, SPI, BCD conversion', start: 'lesson 9, project 05',
    how: 'Measure an input pin and show the frequency on a 7-segment display driven over SPI.' },
  { t: 'Tone keyboard', d: 2, cat: 'Sound', parts: 'buttons, a small speaker or I2S amplifier', learn: 'DDS, debouncing', start: 'lesson 10, project 08',
    how: 'Each button sets a DDS step for a note; mix several for chords.' },
  { t: 'Knight Rider on a strip', d: 1, cat: 'Display', parts: 'a WS2812 strip', learn: 'animation, memory', start: 'project 01',
    how: 'A bright dot with a fading tail that bounces along 60 LEDs.' },
  { t: 'Logic probe', d: 1, cat: 'Instruments', parts: 'a wire', learn: 'synchronizers, edge counting', start: 'lesson 3 + 9',
    how: 'Show on the LEDs whether a pin is high, low, toggling or floating (with the pull-up switched).' },
  { t: 'PID fan control', d: 2, cat: 'Control', parts: 'a 4-pin PC fan', learn: 'PWM, tachometer, feedback', start: 'I/O view (fans), lesson 4',
    how: 'Hold the chip temperature at 50 C by adjusting the fan PWM; measure the fan speed from its tach pin.' },
  { t: 'UART to WS2812 bridge', d: 2, cat: 'Communication', parts: 'USB-UART cable, LED strip', learn: 'UART receiver, FIFOs', start: 'lesson 7, project 01',
    how: 'Send colours from a PC program over serial; the FPGA puts them on the strip.' },
  { t: 'Oscilloscope', d: 3, cat: 'Instruments', parts: 'an ADC module (AD9226 or an SPI ADC)', learn: 'sampling, triggers, block RAM', start: 'lesson 8, Tools logic analyzer',
    how: 'Fill block RAM with samples after a trigger and draw them in the app (print values for the Plotter or a web page).' },
  { t: 'VGA Game of Life', d: 2, cat: 'Display', parts: 'VGA monitor, 8 resistors', learn: 'video timing, memory', start: 'projects 07 + 15',
    how: 'Draw the 64 x 64 grid as big pixels; let the generations run at 30 per second.' },
  { t: 'Pong on VGA', d: 3, cat: 'Games', parts: 'VGA monitor, 2 encoders or buttons', learn: 'video, collision logic, state machines', start: 'projects 07 + 03',
    how: 'Ball and paddles as rectangles compared with the pixel counters; a state machine for the game.' },
  { t: 'Audio spectrum analyzer', d: 3, cat: 'Sound', parts: 'I2S microphone', learn: 'filters, the FFT', start: 'projects 08 + 14',
    how: 'A bank of band-pass filters (project 14) or an FFT; show the bands as bars on LEDs or VGA.' },
  { t: 'SHA-256 proof of work for messages', d: 1, cat: 'Computing', parts: 'nothing', learn: 'hashing, nonces', start: 'project 13',
    how: 'Find a nonce that gives your message a hash with 24 zero bits; anyone can check it with Python in a millisecond.' },
  { t: 'Software radio receiver', d: 3, cat: 'Radio', parts: 'a fast ADC, an antenna filter', learn: 'mixing, filters, decimation', start: 'project 14, project 12',
    how: 'Mix the ADC signal down with a DDS, filter with the FIR, decimate, demodulate AM in Python.' },
  { t: 'Stepper plotter', d: 3, cat: 'Motion', parts: '2 steppers, drivers, pen', learn: 'motion profiles, coordination', start: 'project 04',
    how: 'Move two axes together along lines (Bresenham); Python sends the path.' },
  { t: 'RISC-V programs', d: 2, cat: 'Computing', parts: 'nothing', learn: 'machine code, processors', start: 'project 10',
    how: 'Write your own assembly for the FPGA\'s RISC-V core: a prime sieve, a LED pattern, a UART echo.' },
  { t: 'Bitcoin header race', d: 2, cat: 'Computing', parts: 'nothing', learn: 'parallel hardware, timing', start: 'project 13',
    how: 'Add miner units until the chip is full; plot hashes per second against LUTs used.' },
  { t: 'Capacitive touch keyboard', d: 2, cat: 'Sensors', parts: 'copper pads, resistors', learn: 'measuring charge times', start: 'project 09',
    how: 'Each pad is a touch key; play notes with lesson 10\'s oscillator.' },
  { t: 'Weather station', d: 2, cat: 'Sensors', parts: 'BME280 (I2C)', learn: 'I2C, Python, logging', start: 'project 05, Tools I2C',
    how: 'Read temperature, humidity and pressure every minute, log to a file, graph in the Plotter.' },
  { t: 'Network sound to FM', d: 1, cat: 'Radio', parts: 'nothing', learn: 'AES67, RDS', start: 'project 12',
    how: 'Your PC\'s music to an FM radio with your own station name: already built, add RDS text from the song titles.' },
  { t: 'Hardware random numbers', d: 2, cat: 'Computing', parts: 'nothing', learn: 'ring oscillators, entropy', start: 'lesson 2',
    how: 'Free-running ring oscillators sampled by the clock give jitter; test the bits with Python statistics.' },
];
