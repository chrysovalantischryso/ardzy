# What it does

A **neural network**, the same kind of AI that reads handwriting and recognises faces, runs **inside the FPGA**. It looks at a picture of a handwritten digit and says which digit it is:

- **64 multipliers work at the same time**, and one digit takes **963 clocks = 9.6 microseconds**. The ARM with numpy needs far longer for the same math.
- **Draw digits in your browser** (PC or phone): the board serves a drawing page at `http://ardzy.local:8080`. You see the answer, how sure the network is, the 28 x 28 picture it really looks at, and its 64 hidden neurons.
- The FPGA's answer is checked against the same math in Python: **every number equal, to the last bit**.
- **Train your own network** on the PC with `make_model.py` (numpy only, about 2 minutes).

Nothing to connect. LED 0 flashes for every digit.

# How it works

## 1. A neuron

A neuron multiplies each input by a **weight**, adds everything up, adds a **bias**, and keeps the result only if it is positive (this is called **ReLU**). Learning means finding weights that make the right neurons fire.

<figure>
<svg viewBox="0 0 860 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="One neuron">
<defs><marker id="ah16" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<rect x="10" y="20" width="120" height="34" rx="6" class="d-box"/><text x="70" y="42" class="d-mono" text-anchor="middle">pixel 0</text>
<rect x="10" y="70" width="120" height="34" rx="6" class="d-box"/><text x="70" y="92" class="d-mono" text-anchor="middle">pixel 1</text>
<text x="70" y="130" class="d-small" text-anchor="middle">...</text>
<rect x="10" y="146" width="120" height="34" rx="6" class="d-box"/><text x="70" y="168" class="d-mono" text-anchor="middle">pixel 783</text>
<path d="M130 37 L356 95" class="d-arrow" marker-end="url(#ah16)" color="#b8860b"/><text x="240" y="55" class="d-small" text-anchor="middle">x weight</text>
<path d="M130 87 L356 100" class="d-arrow" marker-end="url(#ah16)" color="#b8860b"/>
<path d="M130 163 L356 108" class="d-arrow" marker-end="url(#ah16)" color="#b8860b"/>
<rect x="360" y="60" width="170" height="80" rx="8" class="d-pl"/><text x="445" y="92" class="d-title" text-anchor="middle">add them all</text><text x="445" y="114" class="d-small" text-anchor="middle">+ bias</text>
<path d="M530 100 H596" class="d-arrow" marker-end="url(#ah16)" color="#b8860b"/>
<rect x="600" y="60" width="120" height="80" rx="8" class="d-box"/><text x="660" y="92" class="d-title" text-anchor="middle">ReLU</text><text x="660" y="114" class="d-small" text-anchor="middle">below 0 -> 0</text>
<path d="M720 100 H786" class="d-arrow" marker-end="url(#ah16)" color="#b8860b"/><text x="820" y="104" class="d-mono" text-anchor="middle">h</text>
</svg>
<figcaption>One neuron of the hidden layer: 784 multiplications and additions.</figcaption>
</figure>

## 2. The network

| Layer | Neurons | Each one looks at | Multiplications |
|---|---|---|---|
| input | 784 | the 28 x 28 pixels, 0 (black) .. 255 (white) | |
| hidden | 64 | all 784 pixels | 64 x 784 = 50 176 |
| output | 10 (one per digit) | all 64 hidden neurons | 10 x 64 = 640 |

The answer is the output neuron with the highest **score**. The page turns the scores into percentages (softmax).

The weights are **8-bit integers** (-127 .. 127), the sums 32-bit. A network trained with floats on the PC is turned into these integers by `make_model.py`; it reads digits just as well, and integers are what hardware does fast and small.

## 3. Why the FPGA is fast at this

The FPGA has **16 lanes**. Each lane has its own block RAM with the weights of 4 hidden neurons, and reads **4 weights per clock** (one 32-bit word). The same 4 pixels go to all 16 lanes at once, so **64 multiplications happen in every clock**:

<figure>
<svg viewBox="0 0 860 230" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The 16 lanes">
<defs><marker id="ah16b" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<rect x="10" y="80" width="140" height="70" rx="8" class="d-ps"/><text x="80" y="108" class="d-title" text-anchor="middle">picture</text><text x="80" y="128" class="d-small" text-anchor="middle">4 pixels per clock</text>
<path d="M150 115 H196" class="d-arrow" marker-end="url(#ah16b)" color="#b8860b"/>
<rect x="200" y="20" width="250" height="40" rx="6" class="d-pl"/><text x="325" y="45" class="d-mono" text-anchor="middle">lane 0: RAM + 4 multipliers</text>
<rect x="200" y="68" width="250" height="40" rx="6" class="d-pl"/><text x="325" y="93" class="d-mono" text-anchor="middle">lane 1: RAM + 4 multipliers</text>
<text x="325" y="130" class="d-small" text-anchor="middle">...</text>
<rect x="200" y="150" width="250" height="40" rx="6" class="d-pl"/><text x="325" y="175" class="d-mono" text-anchor="middle">lane 15: RAM + 4 multipliers</text>
<path d="M450 105 H526" class="d-arrow" marker-end="url(#ah16b)" color="#b8860b"/>
<rect x="530" y="60" width="150" height="90" rx="8" class="d-box"/><text x="605" y="92" class="d-title" text-anchor="middle">16 sums</text><text x="605" y="114" class="d-small" text-anchor="middle">16 neurons ready</text><text x="605" y="132" class="d-small" text-anchor="middle">every 196 clocks</text>
<path d="M680 105 H726" class="d-arrow" marker-end="url(#ah16b)" color="#b8860b"/>
<rect x="730" y="60" width="120" height="90" rx="8" class="d-acc"/><text x="790" y="92" class="d-title" text-anchor="middle">layer 2</text><text x="790" y="114" class="d-small" text-anchor="middle">10 scores</text>
<text x="430" y="218" class="d-small" text-anchor="middle">layer 1: 4 rounds of 196 clocks (16 neurons per round); layer 2: 10 x 16 clocks; plus the pipeline = 963 clocks</text>
</svg>
<figcaption>Spatial parallelism: the same small circuit 16 times, all working in the same clock.</figcaption>
</figure>

Each lane is a **pipeline**: clock 1 the RAMs answer, clock 2 four products, clock 3 their sum, clock 4 add it to the neuron's total. A new word enters every clock, so the pipeline never waits. At the end of a neuron: add the bias, divide by 2^SHIFT (a shift), keep 0 .. 255.

## 4. How it learned

There is no downloaded data set: `make_model.py` makes 60 000 training digits itself, written in about 250 Windows fonts and drawn as pen strokes, each turned, slanted, thinner or bolder. Then it trains the network (24 rounds, a few seconds each with numpy) and checks it on digits from fonts it never saw: **99.9 % right**. Real handwriting is harder: draw some and see.

# Try it

Nothing to wire. **Upload and run**. The Monitor shows 50 test digits with the FPGA's answers, the speed against the ARM, and then:

    3. Draw a digit: open  http://ardzy.local:8080  in a browser

Open that page on the PC or on a phone, draw a digit big and in the middle, lift the pen. **Show an example** draws one of the test digits.

# Program it

```python
import nn_model
from blocks import Bus, DigitAI, nn_load_model, nn_reference, digit_preprocess
ai = DigitAI(Bus(), slot=1)
m = nn_load_model(nn_model)
ai.load(m)                          # 50 KB of weights into the FPGA
d = ai.run(m['test'][0])            # a 28 x 28 picture (784 values 0..255) -> the digit
print(d, ai.scores(), ai.cycles())  # the 10 scores, the clocks it took
print(nn_reference(m, m['test'][0]))   # the same math in Python: (digit, scores, hidden)
x = digit_preprocess(img)           # any drawing (2-D array, ink bright) -> 28 x 28 like the training
```

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | write 1: start (write the picture first) |
| 1 | STATUS | [0] busy [1] a result is ready |
| 2, 3 | RESULT, CYCLES | the digit; the clocks it took |
| 4 | SHIFT | the hidden layer's scale (divide by 2^SHIFT) |
| 5 | COUNT | digits read since power-on |
| 6, 7 | WADDR, WDATA | load weights: the address, then words (the address counts up) |
| 16 .. 25 | SCORE[k] | the 10 scores (signed) |
| 64 .. 79 | HIDDEN | the 64 hidden values, 4 per word |
| 128 .. 191, 192 .. 201 | B1, B2 | the biases |
| 256 .. 451 | PICTURE | 196 words, 4 pixels each |
| 1023 | ID | "NNET" |

# Learn from it

| Idea | Where to see it |
|---|---|
| A neuron = multiply, add, bias, ReLU | `nn_reference()` in `blocks.py` (5 lines of numpy) |
| Spatial parallelism: 16 lanes | `nn_engine.v`: `generate for (l = 0; l < LANES ...)` |
| A pipeline: one word per clock | `dv`, `pv`, `sv`, `f1`, `f2` |
| Integers instead of floats (quantisation) | `quantize()` in `make_model.py` |
| Training: gradient descent | `train()` in `make_model.py` |
| Bit-exact checking against a model | `selftest.py`, `sim/run_sim.py` |

## Exercises

1. **How many operations per second?** One digit is 50 816 multiplications in 9.6 microseconds. How many per second is that?

<details><summary>Answer</summary>
About 5.3 billion multiply-adds per second (64 per clock at 100 MHz = 6.4 billion when the pipeline is full), from a chip of a few watts.
</details>

2. **Make it fail.** Draw a 7 with a cross bar, a 1 with a long flag, a very small digit in a corner. Which ones does it read wrong? Why does the cut-out and centring (`digit_preprocess`) help with the small one?

3. **More neurons.** In `make_model.py` set `HID = 32` and train. How right is it? What would `HID = 128` need in the FPGA? (Hint: 8 rows per lane, 1568 words per RAM.)

<details><summary>Answer</summary>
With 32 neurons it is still above 99 % on the made-up test digits but weaker on real drawings. 128 neurons need 2 block RAMs per lane (32 of the 60) and twice the clocks for layer 1, about 1750 in all: still under 20 microseconds.
</details>

4. **Look inside.** Read `ai.hidden()` for a 1 and for an 8. Which neurons fire for both? Which only for one?

# Ideas

- Letters: train on A .. Z (26 outputs) with the same fonts.
- A camera (USB webcam on the board) reading digits on paper.
- Show the drawing and the answer on a VGA monitor (project 07).

# If something is wrong

- **The page does not open**: is the demo running (the Monitor shows "3. Draw a digit")? Use the address it prints. A phone must be on the same network as the board.
- **Wrong digits**: draw big, in the middle, one digit at a time. Thin lines and digits touching the edge are harder.
- **"The FPGA does not hold the NNET project"**: upload this project again.
