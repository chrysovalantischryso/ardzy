# What it does

A lab bench for **AXI-Stream**, the way data flows between blocks in FPGA designs (Xilinx IP, video, network, DSP chains all use it). Three small chains show the building blocks of the Ardzy library at work: FIFOs, a width converter, a CRC-32 engine checked against Python, a source that makes 100 million words per second with a meter that checks every one, and an arbiter that merges two streams without breaking their frames.

# How it works

A stream moves one word when the source has data (**tvalid**) and the sink can take it (**tready**) at the same clock edge. **tlast** marks the last word of a frame (a packet). Either side may wait: that is **back pressure**, and it is what makes streams safe to connect in any order.

```
          tdata[31:0] ------------>
source    tvalid      ------------>    sink        a word moves when tvalid AND tready
          tlast       ------------>
          tready      <------------
```

The three chains:

| Chain | Path | What it shows |
|---|---|---|
| A | ARM -> FIFO -> 32 to 8 bits -> CRC-32 | the CRC of each frame, the same number as Python's `zlib.crc32` |
| B | counter source -> FIFO -> meter | 100 million words per second; with back pressure (the meter takes a word only every n clocks) nothing is lost |
| C | two sources -> arbiter -> FIFO -> ARM | frames of 3 and 5 words arrive whole, the sources take turns |

The blocks (in `ardzy_axis.v`, ready for your own designs): `ardzy_axis_fifo`, `ardzy_axis_32to8`, `ardzy_axis_crc32`, `ardzy_axis_arb2`, `ardzy_axis_counter`, `ardzy_axis_meter`.

# Try it

Nothing to wire. **Upload and run**: the Monitor shows the CRC of a text (FPGA and Python agree), the speed of chain B at 1, 2, 4 and 10 clocks per word, and the frames of chain C.

# Program it

```python
from blocks import Bus, StreamLab
import zlib
lab = StreamLab(Bus(), slot=1)
lab.reset()
data = b'Hello, stream!  '
print(hex(lab.crc_frame(data)), hex(zlib.crc32(data)))
lab.sources(b=True)
lab.slow(3)                         # the meter takes 1 word in 4 clocks
print(lab.meter())                  # words per second, errors
```

Use the blocks in your own design: copy the project, and in `top.v` chain them with the `tdata / tvalid / tready / tlast` wires, as `streamlab.v` does.

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] reset [1] source B on [2] sources C on |
| 1, 2 | IN_DATA, IN_LAST | a word into chain A / the last word of a frame |
| 3..5 | CRC, CRC_FRAMES, CRC_BYTES | (read) |
| 6..8 | B_PER_SEC, B_WORDS, B_ERRORS | the meter |
| 9, 10 | B_SLOW, B_LEN | back pressure, frame length |
| 11..13 | C_DATA, C_LEVEL, C_INFO | take a word from chain C |
| 14 | A_LEVEL | words waiting in chain A |
| 15 | ID | "AXIS" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Handshake: data moves only when valid and ready | tvalid / tready on every stream |
| Back pressure | the meter takes a word only every n clocks; nothing is lost |
| FIFOs decouple producers and consumers | `ardzy_axis_fifo` between every pair of blocks |
| Frames and arbitration | tlast marks the end of a frame; the arbiter never splits one |

## Exercises

1. A source offers 100 million words per second, the sink takes 1 in 4 clocks. What happens to the source?

<details><summary>Answer</summary>
It sees tready low 3 clocks in 4 and waits: 25 million words per second pass, none lost. That is back pressure.
</details>

2. Why does CRC-32 detect any single changed bit in a frame?

<details><summary>Answer</summary>
CRC is the remainder of a polynomial division; a single changed bit adds a term the generator polynomial cannot divide, so the remainder always changes.
</details>

3. Why must a block never lower tvalid or change tdata before the word is taken?

<details><summary>Answer</summary>
The sink may take it at any later clock; changing it early would lose or corrupt that word. The rule makes any two blocks safe to connect.
</details>

# Ideas

- A packet filter: pass only frames whose first word matches.
- A moving average or FIR filter as a stream block between the source and the meter.
- Feed the FM radio's audio from a stream.

# If something is wrong

- The self-test checks every block; if your own chain loses words, look for a block that ignores tready (it must hold tvalid and the data until the word is taken).
