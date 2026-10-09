# What it does

A **language model**, the idea behind chatbots, made small enough for the FPGA. It reads the last 16 letters and gives every letter it knows a **score**: how likely it is to come next. Writing is just that, over and over: guess, pick a letter, add it, guess again.

- The three layers of the network (126 000 weights) run in the FPGA's **general network engine**: 64 multiplications per clock, one letter in about **21 microseconds**.
- In the Ardzy app (**Ready projects**, Text AI, **Open**): type the start of a sentence and let it write on; choose how adventurous it is; type and watch its guesses for the next letter.
- It learned from the Ardzy guides and lessons and from the documentation inside Python itself, so it writes things that sound like... computer documentation. **Train it on your own text** with `make_model.py --text yourfile.txt`.
- The FPGA's answer is checked against the same math in Python: **every score equal, to the last bit**.

It is tiny compared with a chatbot (126 thousand weights against billions), so expect English-looking words and half-sentences with a wink of meaning, not answers to questions.

Nothing to connect. LED 0 flashes while it thinks.

# How it works

## 1. From letters to numbers

The model knows 48 letters (a .. z, digits, space, punctuation; everything is lower case). Each letter has an **embedding**: 12 numbers that were learned in training, so that letters which behave alike (vowels, digits ...) get similar numbers. The last 16 letters become 16 x 12 = **192 numbers**. That small table lookup is done by the ARM.

## 2. The network

| Layer | Neurons | Looks at | Weights |
|---|---|---|---|
| 1 | 256 (ReLU) | the 192 numbers | 49 152 |
| 2 | 256 (ReLU) | layer 1 | 65 536 |
| 3 | 48, one per letter (scores) | layer 2 | 12 288 |

## 3. Picking a letter: the temperature

The scores become probabilities (softmax). Then a letter is **drawn by lot**, the likely ones more often. The **temperature** decides how much: low (0.3) always takes nearly the most likely letter (safe, but it repeats itself), high (1.2) gives rare letters a chance (lively, then nonsense). Around 0.6 to 0.8 reads best.

## 4. The general network engine

Project 16's engine could run one network shape. This one (`mlp_engine.v`) runs **any** network of up to 4 layers: for every layer the ARM sets how many inputs and outputs, where its weights are, the shift and the activation (none, ReLU or sigmoid). The same 16 lanes with 64 multiplications per clock do all layers one after the other; the values between layers go back and forth between two buffers inside the lanes. Project 18 uses the same engine for pictures.

Signed numbers as bytes: the engine's inputs are bytes 0 .. 255, the embeddings are signed. So the ARM sends `value + 128`, and the extra `128 x (sum of the weights)` is taken off again through layer 1's biases (`make_model.py`, `quantize`). The result is exactly the same.

# Try it

**Upload and run**: the Monitor shows the bit-for-bit check, three texts it writes, and the speed. Then use the app: Ready projects, Text AI, **Open**.

# Train it on your own text

On the PC, in this project's folder:

    python make_model.py --text mystories.txt

Any plain text works; more is better (a few hundred KB or more). It takes a few minutes. Then **Upload and run** again: the new `text_model.py` goes to the board.

# Program it

```python
import base64, numpy as np, text_model as tm
from blocks import Bus, MLP, mlp_reference
nn = MLP(Bus(), slot=1)
dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), np.int8).reshape(shape)
layers = [{'w': dec(getattr(tm, 'W%d' % (k + 1)), tm.SHAPES[k]), 'b': getattr(tm, 'B%d' % (k + 1)),
           'shift': tm.SHIFTS[k], 'act': tm.ACTS[k]} for k in range(3)]
nn.use(nn.load(layers))                 # the network into the engine
best, scores = nn.run(input_bytes)      # 192 bytes in, 48 scores out (and the best one)
```

## Registers (slot 1, the general engine)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | write 1: run the network |
| 1 | STATUS | [0] busy [1] a result is ready |
| 2, 3 | RESULT, CYCLES | the largest score's index; clocks of the last run |
| 4 | LAYERS | 1 .. 4 |
| 5 | COUNT | runs since power-on |
| 6, 7 | WADDR, WDATA | load weights (lane x 2048 + word) and biases (0x10000 + lane x 128 + n) |
| 16 + 8L .. 21 + 8L | layer L | IN4, OG, WBASE, BBASE, SHIFT, ACT |
| 256 .. 511, 512 .. 767 | buffers A, B | the input (A) and the values between layers |
| 768 .. 1022 | SCORES | the last layer's results |
| 1023 | ID | "MLP1" |

# Learn from it

| Idea | Where to see it |
|---|---|
| A language model: guess the next letter | `scores()` and `write()` in `main.py` |
| Embeddings | `EMBED` in `text_model.py`, `emb[ids]` |
| Temperature and sampling | `probs()` in `main.py` |
| One engine for any network | `mlp_engine.v`: the layer registers, `S_SETUP` |
| Training with backpropagation | `train()` in `make_model.py` |

## Exercises

1. **Temperature.** Write the same start at 0.2, 0.7 and 1.5. When does it repeat itself? When does it stop making words?
2. **Context.** It sees only 16 letters. Can it close a bracket opened 30 letters earlier? Try it.
3. **Your text.** Train it on a song text, a recipe collection or your own messages (`--text`). How many rounds before it writes your words?

<details><summary>What to expect</summary>
Low temperature loops ("the the the" or one favourite sentence); high temperature invents words. With 16 letters of memory it forgets the start of long sentences; real language models see thousands of words. Common words of your text appear after a few rounds; its style after more.
</details>

# If something is wrong

- **The page in the app says the AI is not running**: press **Upload and run** and wait a few seconds.
- **Strange letters**: it only knows the 48 letters it learned; others in your start are left out.
- **"The FPGA does not hold the TEXT project"**: upload this project again.
