# What it does

**Conway's Game of Life** (1970) is a grid of cells, each alive or dead, and four rules. From them come patterns that stay still, blink, fly across the grid, and even guns that shoot gliders for ever. This project runs it in hardware on a 64 x 64 grid whose edges wrap around (a torus):

- A whole **row of 64 cells per clock**, about **1.43 million generations per second**, thousands of times faster than the same rules in Python.
- Famous patterns by name (glider, spaceship, pulsar, Gosper glider gun, R-pentomino ...), random soup, your own drawings.
- The grid shown in the Monitor with block characters.

Nothing to connect. LED 0 flickers while it runs.

# How it works

## 1. The rules

Every cell has 8 neighbours. For the next generation, at the same moment for all cells:

| This cell | Live neighbours | Next generation |
|---|---|---|
| alive | 2 or 3 | stays alive |
| alive | 0, 1 (lonely) or 4 .. 8 (crowded) | dies |
| dead | exactly 3 | is born |
| dead | any other number | stays dead |

<figure>
<svg viewBox="0 0 860 170" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A glider over four generations">
<g transform="translate(20,20)">
<text x="0" y="-5" class="d-small">generation 0</text>
<rect x="0" y="0" width="100" height="100" class="d-box"/>
<rect x="40" y="0" width="20" height="20" class="d-pl"/><rect x="60" y="20" width="20" height="20" class="d-pl"/><rect x="20" y="40" width="20" height="20" class="d-pl"/><rect x="40" y="40" width="20" height="20" class="d-pl"/><rect x="60" y="40" width="20" height="20" class="d-pl"/>
</g>
<g transform="translate(190,20)">
<text x="0" y="-5" class="d-small">1</text>
<rect x="0" y="0" width="100" height="100" class="d-box"/>
<rect x="20" y="20" width="20" height="20" class="d-pl"/><rect x="60" y="20" width="20" height="20" class="d-pl"/><rect x="40" y="40" width="20" height="20" class="d-pl"/><rect x="60" y="40" width="20" height="20" class="d-pl"/><rect x="40" y="60" width="20" height="20" class="d-pl"/>
</g>
<g transform="translate(360,20)">
<text x="0" y="-5" class="d-small">2</text>
<rect x="0" y="0" width="100" height="100" class="d-box"/>
<rect x="60" y="20" width="20" height="20" class="d-pl"/><rect x="20" y="40" width="20" height="20" class="d-pl"/><rect x="60" y="40" width="20" height="20" class="d-pl"/><rect x="40" y="60" width="20" height="20" class="d-pl"/><rect x="60" y="60" width="20" height="20" class="d-pl"/>
</g>
<g transform="translate(530,20)">
<text x="0" y="-5" class="d-small">3</text>
<rect x="0" y="0" width="100" height="100" class="d-box"/>
<rect x="40" y="20" width="20" height="20" class="d-pl"/><rect x="60" y="40" width="20" height="20" class="d-pl"/><rect x="80" y="40" width="20" height="20" class="d-pl"/><rect x="40" y="60" width="20" height="20" class="d-pl"/><rect x="60" y="60" width="20" height="20" class="d-pl"/>
</g>
<g transform="translate(700,20)">
<text x="0" y="-5" class="d-small">4: the same shape, 1 down and 1 right</text>
<rect x="0" y="0" width="100" height="100" class="d-box"/>
<rect x="60" y="20" width="20" height="20" class="d-pl"/><rect x="80" y="40" width="20" height="20" class="d-pl"/><rect x="40" y="60" width="20" height="20" class="d-pl"/><rect x="60" y="60" width="20" height="20" class="d-pl"/><rect x="80" y="60" width="20" height="20" class="d-pl"/>
</g>
<text x="430" y="160" class="d-small" text-anchor="middle">a glider: after 4 generations it is back, one cell further down and right. Nothing in the rules says "move".</text>
</svg>
<figcaption>Five cells and four rules make something that travels.</figcaption>
</figure>

## 2. Why hardware is fast at this

In Python, each of the 4096 cells needs its 8 neighbours counted one after the other: about 50 000 small steps per generation. In the FPGA, the rule for a cell is a little circuit (an 8-input adder and a compare, about 15 LUTs). The design has **64 copies** of it, one per column, all working in the same clock.

<figure>
<svg viewBox="0 0 860 230" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The life engine">
<defs><marker id="ah15" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<rect x="10" y="20" width="150" height="190" rx="8" class="d-ps"/><text x="85" y="45" class="d-title" text-anchor="middle">bank A</text><text x="85" y="65" class="d-small" text-anchor="middle">64 rows x 64 bits</text><text x="85" y="85" class="d-small" text-anchor="middle">(the grid now)</text>
<path d="M160 115 H216" class="d-arrow" marker-end="url(#ah15)" color="#b8860b"/><text x="188" y="105" class="d-small" text-anchor="middle">a row</text><text x="188" y="135" class="d-small" text-anchor="middle">per clock</text>
<rect x="220" y="40" width="190" height="34" rx="6" class="d-box"/><text x="315" y="62" class="d-mono" text-anchor="middle">above (row r-1)</text>
<rect x="220" y="98" width="190" height="34" rx="6" class="d-box"/><text x="315" y="120" class="d-mono" text-anchor="middle">here  (row r)</text>
<rect x="220" y="156" width="190" height="34" rx="6" class="d-box"/><text x="315" y="178" class="d-mono" text-anchor="middle">below (row r+1)</text>
<path d="M410 115 H466" class="d-arrow" marker-end="url(#ah15)" color="#b8860b"/>
<rect x="470" y="60" width="180" height="110" rx="8" class="d-pl"/><text x="560" y="95" class="d-title" text-anchor="middle">64 x the rule</text><text x="560" y="117" class="d-small" text-anchor="middle">count 8 neighbours,</text><text x="560" y="135" class="d-small" text-anchor="middle">alive or dead</text>
<path d="M650 115 H696" class="d-arrow" marker-end="url(#ah15)" color="#b8860b"/>
<rect x="700" y="20" width="150" height="190" rx="8" class="d-acc"/><text x="775" y="45" class="d-title" text-anchor="middle">bank B</text><text x="775" y="65" class="d-small" text-anchor="middle">new row r</text><text x="775" y="85" class="d-small" text-anchor="middle">(the next grid)</text>
<text x="430" y="222" class="d-small" text-anchor="middle">after row 63 the banks swap: B becomes the grid, A receives the next generation</text>
</svg>
<figcaption>A generation: 64 rows, one per clock, plus 6 clocks to start, finish and swap = 70 clocks, 0.7 microseconds.</figcaption>
</figure>

Three ideas make it work:

- **Two banks (double buffering)**: all cells must change at the same moment, so the new generation is written into the other bank while the old one is still read. Then they swap.
- **A sliding window of three rows**: to make row r, only rows r-1, r and r+1 are needed. Each clock the window slides down by one row.
- **Wrap-around**: column 0's left neighbour is column 63, row 0's upper neighbour is row 63; a glider leaving the right edge comes back on the left.
- **A pipeline**: the row below is read from memory one clock ahead into a register, and each new row is written (and its live cells counted) one clock after it was made. The first version did the memory read, the rule, the count and the write in a single clock: the build tools reported only 61 MHz, too slow for the 100 MHz clock. Split over three clocks, each part has 10 ns to itself.

# Try it

Nothing to wire. **Upload and run**. The Monitor shows still lifes, oscillators and spaceships, then a race (100 generations in Python against the FPGA), then a Gosper glider gun, then random soup for ever.

Draw your own pattern in `main.py`:

```python
life.clear()
life.place(['.##', '##.', '.#.'], row=30, col=30)    # the R-pentomino: 5 cells, 1103 generations of chaos
life.steps(100)
print(Life.text(life.read()))
```

# Program it

```python
from blocks import Bus, Life, LIFE_PATTERNS
life = Life(Bus(), slot=1)
life.clear()                    # or life.randomize(), life.randomize(sparse=True)
life.place('glider', 5, 5)      # a name from LIFE_PATTERNS or rows of '#' and '.'
life.steps(10)                  # 10 generations (waits)
g = life.read()                 # 64 ints, bit c of row r = the cell
life.run(per_second=10)         # runs on its own; life.run() = flat out; life.stop()
print(life.generation(), life.population(), life.per_second())
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | write: [0] clear [1] run [2] random fill [3] sparse fill |
| 1 | STATUS | [0] busy [1] running |
| 2 | STEPS | write n: do n generations |
| 3, 4 | GENERATION, POPULATION | counters |
| 5 | RATE | clocks between generations while running |
| 6 | PER_SEC | generations in the last second |
| 64 + 2r, 65 + 2r | row r | bits 0 .. 31 and 32 .. 63 |
| 1023 | ID | "LIFE" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Spatial parallelism: one circuit per column | `life.v`: the `for` loop that makes `next_row` (64 copies) |
| Double buffering | `bank0`, `bank1` and `cur` |
| A sliding window over memory | `above`, `here`, `below` |
| A state machine that walks through memory | `S_P0`, `S_P1`, `S_RUN`, `S_DONE` |
| Emergence: simple local rules, complex behaviour | run the R-pentomino or the acorn |

## Exercises

1. **Still life or oscillator?** Place a `block`, a `beehive`, a `blinker` and a `toad`. Step 1, 2 and 3 generations and compare with `life.read()`. Which never change, which come back after 2?

<details><summary>Answer</summary>
Block and beehive are still lifes (period 1); blinker and toad are oscillators with period 2. The pulsar has period 3.
</details>

2. **Count the clocks.** A generation takes 70 clocks at 100 MHz. How many generations per second? Check with `life.per_second()` after `life.run()`.

3. **The R-pentomino.** Place it in an empty grid and print the population every 100 generations. When does it settle? (On an infinite grid it takes 1103 generations; on this small torus the debris crashes into itself, so the answer differs.)

4. **A wider rule.** "HighLife" adds one birth rule: a dead cell with **6** neighbours is also born. In `life.v` change `(n == 4'd3)` to `(n == 4'd3) || (n == 4'd6 && !here[i])`, build, and look for the "replicator" pattern `['..###', '.#..#', '#...#', '#..#.', '###..']`.

5. **Bigger grid.** What would a 128 x 128 grid cost? (Hint: 128 copies of the rule, banks of 128-bit rows.)

<details><summary>Answer</summary>
Twice the rule circuits (about 2000 LUTs instead of 1000) and four times the memory (2 x 16 384 bits); a generation would take 134 clocks. It fits the XC7Z010 easily; 512 x 512 would need block RAM instead of LUT RAM.
</details>

# Ideas

- Show the grid on a VGA monitor with project 07's video block (one pixel block per cell).
- Draw with an encoder knob (project 03) or from the app.
- Find the longest-lived soup: run thousands of random grids flat out, keep the seed that lasts longest.

# If something is wrong

- **The grid does not change**: was it empty, or a still life? Try `life.randomize()`.
- **Rows read as 0**: rows can only be read while no generation is running; `life.stop()` first.
