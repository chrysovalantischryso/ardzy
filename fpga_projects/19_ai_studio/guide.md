# What it does

Projects 16, 17 and 18 keep their networks in the FPGA's own block RAM: 128 KB, so the networks are small and only one fits at a time. The board has much more memory: **512 MB of DDR**, of which Linux uses about 45 MB. AI Studio puts the networks there:

- **Three big networks at once**, 2 MB of weights in all: a digit reader 10 times bigger than project 16's, a text model 8 times bigger than project 17's (it remembers 32 letters instead of 16), a drawer 7 times bigger than project 18's.
- **No re-uploading**: in the Ardzy app's AI page, Read, Write and Draw all work at the same time.
- **Learn my handwriting**: every digit you draw and mark Right or Wrong is kept; one button teaches the reader your way of writing.
- Every result is checked against the same math in Python, **to the last bit**, like in the other AI projects.

Nothing to connect. LED 0 lights while a network runs.

# How it works

## 1. The FPGA reads the DDR by itself

The Zynq has **HP ports**: four 64-bit doors through which the FPGA reads (and could write) the DDR memory without the ARM. A test on this board measured 800 MB/s through one port and 3.2 GB/s through all four. AI Studio uses two of them (HP0 and HP2): with all four, the many wires at the edge of the ARM part of the chip could not be routed together with the engine.

The FPGA only reads here, so it can never damage Linux's memory.

## 2. Memory the FPGA can find

The program on the board takes 16 MB of its own memory and **locks** it (`mlock`): Linux may then never swap it out or move it. Linux gives memory in 4 KB **pages** scattered over the DDR, so the program reads, from `/proc/self/pagemap`, which physical page each 4 KB of its memory is in. That list (4096 pages) goes into a **page table** in the FPGA; the engine uses it to find every byte.

One more step: the ARM writes through its caches, the HP ports read the DDR itself. After the networks are copied in, the program writes 8 MB of other memory, which pushes the ARM's caches out to the DDR (`DDRStore.flush`).

## 3. The weights flow while the network runs

The engine has the same 16 lanes as the other AI projects. Their weights now come from two streams, one per HP port (HP0 carries lanes 0 .. 7, HP2 lanes 8 .. 15). For every group of 16 neurons a stream holds one **bias row**, then one **weight row** per 4 inputs; the layers of a network follow each other, so the stream never stops between layers. Each port's words go past its 8 lanes, and every lane keeps its own 4 bytes as they pass (the first version built every 64-byte row in one place and sent it to all lanes: 512 wires across the chip, and it would not route).

<figure>
<svg viewBox="0 0 860 210" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The DDR engine">
<defs><marker id="ah19" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<rect x="10" y="40" width="150" height="130" rx="8" class="d-ps"/><text x="85" y="70" class="d-title" text-anchor="middle">DDR 512 MB</text><text x="85" y="92" class="d-small" text-anchor="middle">3 networks,</text><text x="85" y="110" class="d-small" text-anchor="middle">2 MB of weights</text><text x="85" y="128" class="d-small" text-anchor="middle">(locked pages)</text>
<path d="M160 70 H236" class="d-arrow" marker-end="url(#ah19)" color="#b8860b"/><path d="M160 95 H236" class="d-arrow" marker-end="url(#ah19)" color="#b8860b"/>
<path d="M160 120 H236" class="d-arrow" marker-end="url(#ah19)" color="#b8860b"/><path d="M160 145 H236" class="d-arrow" marker-end="url(#ah19)" color="#b8860b"/>
<text x="198" y="190" class="d-small" text-anchor="middle">HP0, HP2</text>
<rect x="240" y="50" width="150" height="110" rx="8" class="d-box"/><text x="315" y="85" class="d-title" text-anchor="middle">4 FIFOs</text><text x="315" y="107" class="d-small" text-anchor="middle">+ the page table</text><text x="315" y="125" class="d-small" text-anchor="middle">(evens out the DDR)</text>
<path d="M390 105 H446" class="d-arrow" marker-end="url(#ah19)" color="#b8860b"/>
<rect x="450" y="60" width="140" height="90" rx="8" class="d-box"/><text x="520" y="95" class="d-title" text-anchor="middle">rows</text><text x="520" y="117" class="d-small" text-anchor="middle">64 bytes each</text>
<path d="M590 105 H646" class="d-arrow" marker-end="url(#ah19)" color="#b8860b"/>
<rect x="650" y="40" width="200" height="130" rx="8" class="d-pl"/><text x="750" y="80" class="d-title" text-anchor="middle">16 lanes</text><text x="750" y="102" class="d-small" text-anchor="middle">fed by the</text><text x="750" y="120" class="d-small" text-anchor="middle">two streams</text>
</svg>
<figcaption>The weights never stay in the FPGA: they flow through it, one row of 64 weights every 4 clocks.</figcaption>
</figure>

The **FIFOs** (first in, first out) are what make this work: the DDR answers in bursts, sometimes late (Linux uses it too); each port asks for more as long as its FIFO has room, and the lanes take a row as soon as all four FIFOs have their part. The engine counts the clocks it waited (STALLS).

## 4. Its own clock: 75 MHz

The first AI Studio ran at 100 MHz like every other project. The tools said it would work, but on the board the
results were a little wrong, and different each time; at 77 MHz they were right, every bit. The tools do not know the
timing of the wires to the ARM part exactly. So AI Studio makes its own 75 MHz clock (an MMCM, a clock maker inside
the FPGA, from the 100 MHz clock) and runs on it entirely. The 100 MHz clock is not changed, so the next project you
load finds it as it should be.

| Network | Weights | FPGA (75 MHz) | ARM with numpy |
|---|---|---|---|
| reader | 535 000 | 451 microseconds | about 45 000 |
| text model | 1 032 000 | 867 microseconds per letter | about 83 000 |
| drawer | 539 000 | 456 microseconds | about 45 000 |

About 100 times faster than the ARM, and the engine hardly ever waits for the DDR.

## 5. Learn my handwriting

The reader learned from digits written in fonts and pen strokes, not from you. In the Read tab, mark every answer Right or Wrong (and say which digit it was). **Teach it my handwriting** then fine-tunes the reader on the PC with your drawings, mixed with 3000 practice digits **drawn by the drawer network** (so it does not forget other ways to write), turns it back into the engine's integers and sends it to the board, which switches to it at once. Your drawings stay on your PC (`handwriting.json` next to the app's settings).

# Try it

**Upload and run** (it takes a few seconds more than the others: 2 MB of networks), then in the app: Ready projects, AI Studio, **Open**. The Monitor shows the bit-for-bit check of each network and its speed.

# Program it

```python
import reader_big
from blocks import Bus, MLPDDR, DDRStore
from nn_train import load_layers
store = DDRStore(region=4 << 20)              # 16 MB of locked memory, the FPGA learns its pages
nn = MLPDDR(Bus(), slot=1, store=store)
h = nn.load(load_layers(reader_big))          # into the DDR (as the 4 streams)
nn.ready()                                    # push the ARM's caches out
nn.use(h)
digit, scores = nn.run(pixels)                # 784 bytes in
print(nn.cycles(), nn.stalls())               # clocks, and how many of them it waited for the DDR
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0, 1, 2, 3 | CTRL, STATUS, RESULT, CYCLES | as in project 17's engine |
| 4, 5 | LAYERS, COUNT | |
| 6, 7 | STALLS, ERRORS | clocks waiting for the DDR; DDR answers that were not OKAY |
| 8, 9, 10, 11 | OFS, LEN, REGION, PORTS | the network's place in the streams; 2 HP ports |
| 12, 13 | PTADDR, PTDATA | the page table |
| 16 + 8L, 17 + 8L, 20 + 8L, 21 + 8L | layer L | IN4, OG, SHIFT, ACT |
| 256 .., 512 .., 768 .. | buffers A, B, SCORES | as in project 17 |
| 1023 | ID | "MLP2" |

# Learn from it

| Idea | Where to see it |
|---|---|
| DMA: hardware reading memory by itself | `mlp_ddr.v`: the streamers, `ardzy_ddr.v` |
| Virtual and physical memory, pages | `DDRStore` in `blocks.py` (`/proc/self/pagemap`) |
| Caches and coherence | `DDRStore.flush` |
| FIFOs between a bursty source and a steady consumer | `mlp_fifo`, the row assembler |
| Fine-tuning (transfer learning) | `teach.py` |
| Memory bandwidth as the limit | STALLS: how often the lanes wait |

# If something is wrong

- **"mlock failed" or no physical pages**: the program must run as root (it does when started by the app).
- **WRONG results in the self-test right after loading**: the caches were not pushed out; `nn.ready()` must come after `nn.load()`.
- **Teach it my handwriting is greyed out**: mark at least 10 drawings first.
