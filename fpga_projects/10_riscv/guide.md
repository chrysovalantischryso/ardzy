# What it does

A third processor on the board: a small **RISC-V** (RV32I, the base instruction set) built from FPGA logic, with 16 KB of RAM, a console, the LEDs, 4 output and 4 input pins, a microsecond timer and mailboxes to talk to the ARM. Python on the ARM assembles your program, loads it, starts it and shows what it prints. The demo runs a running light with a greeting, then counts the prime numbers below 12000 with a sieve and compares the time with the same sieve in Python on the ARM.

# How it works

RISC-V is an open instruction set: anyone may build a processor for it. This one is **multi-cycle**: each instruction goes through fetch, decode, execute and memory steps, about 5 clocks, so about 20 million instructions per second at 100 MHz. That is slow next to the ARM (667 MHz, two cores) but it is *exactly* predictable: no caches, no operating system, every instruction always takes the same time. That is what you want for precise timing jobs.

```
ARM (Python)  --writes program-->  16 KB RAM (block RAM, two ports)  <--fetch / load / store--  RISC-V core
              <--console, mail--  peripherals at 0x8000_0000  <--------------------------------
```

- 32 registers x0..x31, all RV32I instructions (add, sub, logic, shifts, compares, branches, jumps, loads and stores of bytes, halves and words).
- ECALL or EBREAK stop the program (the normal way to end); anything unknown stops it with "illegal".
- The ARM can read and write the RAM while the program runs: shared memory.

## The program's addresses

| Address | What |
|---|---|
| 0x0000_0000 .. 0x0000_3FFF | RAM: the program starts at 0, the stack at the top (0x4000) |
| 0x8000_0000 | LEDS (write, 4 bits) |
| 0x8000_0004 / 0x8000_0008 | GPIO out to J8 (write) / GPIO in from J5 (read) |
| 0x8000_000C | CYCLES: a 100 MHz counter |
| 0x8000_0010 | CONSOLE: write a character, it appears in the Monitor |
| 0x8000_0014 / 0x8000_0018 | MAIL_IN (from the ARM) / MAIL_OUT (to the ARM) |
| 0x8000_001C | MICROS: microseconds since the start |

# Try it

**Upload and run**: the LEDs run, then the primes below 12000 are counted on the RISC-V and in Python. The Monitor shows the speed of both.

Write your own: **Copy to my projects**, copy `blink.s` to `mine.s`, change it, add `'mine.s'` to `PROGRAMS` in main.py, Upload.

```
.equ LEDS, 0x80000000
        li   t0, LEDS
        li   t1, 0b0101
        sw   t1, 0(t0)        # LEDs 0 and 2 on
        ebreak                # stop
```

# Program it

```python
from blocks import Bus, RiscV
from riscv import assemble, Sim
rv = RiscV(Bus(), slot=1)
words, labels = assemble(open('blink.s').read())
rv.load(words)
rv.start()
print(rv.wait(timeout=10))     # what the program printed
print(rv.status())             # running, halted, illegal, pc, retired

sim = Sim(words)               # the same program in the Python simulator, for testing
sim.run()
print(sim.console)
```

`riscv.py` is a complete assembler (labels, all RV32I instructions, li, la, call, ret, .word, .ascii, .equ ...) and an instruction-exact simulator. The self-test runs 2000 random instructions on both and compares every register and memory word.

## Registers (slot 1, RAM in slots 2..5)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] run (0 holds the core in reset) |
| 1 | STATUS | [0] running [1] halted [2] illegal |
| 2 | PC | where the program is |
| 3, 4 | CONSOLE, CON_LEVEL | characters printed |
| 5, 6 | MAIL_IN, MAIL_OUT | the mailboxes |
| 7 | RETIRED | instructions done |
| 8 | GPIO | the program's outputs and the LEDs |
| 9 | ID | "RV32" |

# Learn from it

| Idea | Where to see it |
|---|---|
| What a processor is: fetch, decode, execute | the multi-cycle core, about 5 clocks per instruction |
| Memory-mapped peripherals | LEDs, GPIO, console at 0x8000_0000 |
| Shared memory between two processors | the ARM reads and writes the RISC-V's RAM while it runs |
| Machine code | `blink.s`, `primes.s` and the assembler in `riscv.py` |

## Exercises

1. At about 5 clocks per instruction and 100 MHz, how long does a loop of 4 instructions take, 1 million times?

<details><summary>Answer</summary>
4 x 5 x 10 ns x 1 000 000 = 0.2 s.
</details>

2. Why is this slow core still useful next to two 667 MHz ARM cores?

<details><summary>Answer</summary>
It is exactly predictable: no caches, no operating system, no interrupts it did not ask for. A loop always takes the same time, to the nanosecond: good for precise control and for learning.
</details>

3. How does the ARM send a number to a running RISC-V program?

<details><summary>Answer</summary>
It writes MAIL_IN (or any shared RAM word); the program polls the address and reads it. MAIL_OUT works the other way.
</details>

# Ideas

- Let the RISC-V do a precise job (a protocol, a fast loop) while Python does the rest.
- Compile C for it: `riscv64-unknown-elf-gcc -march=rv32i -mabi=ilp32 -nostdlib`, then load the binary words.
- Add the M extension (multiply / divide) to the core using the DSP blocks.

# If something is wrong

- **"illegal" at once**: the program uses an instruction outside RV32I (mul, csr ...) or jumped into data.
- **Nothing printed**: CONSOLE takes one character per write; end the program with `ebreak` so the ARM stops waiting.
