# What it does

Project 16 **reads** handwritten digits. This one does the opposite: it **draws** them. Ask for a 7 and the FPGA draws a new 7, never the same twice, because 16 random numbers decide its style (slant, thickness, size, little hooks).

- The drawing network runs in the FPGA's **general network engine** (the same one as project 17): a whole 28 x 28 picture in about **13 microseconds**.
- Project 16's reader sits **in the same engine**: every drawing is read back at once, so you see whether a "machine reader" agrees with the "machine drawer".
- In the Ardzy app (**Ready projects**, Image AI, **Open**): draw rows of any digit, **morph** one digit slowly into another (a 3 that becomes an 8), and **walk** through styles of one digit.
- Every pixel the FPGA draws is checked against the same math in Python, to the bit.

Nothing to connect. LED 0 flashes while it draws.

# How it works

## 1. Learning to draw: an autoencoder

Training uses two networks. The **encoder** looks at a digit and squeezes it into 16 numbers. The **decoder** gets those 16 numbers plus **which** digit it is, and has to draw the picture back. They learn together, with two goals:

- the drawing must look like the original (the "drawing error"), and
- the 16 numbers must look like ordinary random numbers (the "style spread", called KL in the books).

The second goal is the trick (a **variational** autoencoder): afterwards you can throw the encoder away, give the decoder **any** 16 random numbers, and it draws a believable digit. Because the digit is an input of its own, the 16 numbers only hold the **style** (a "conditional" VAE).

## 2. The drawing network in the FPGA

| Layer | Neurons | Weights | Activation |
|---|---|---|---|
| 1 | 96 | 26 x 96 = 2 496 | ReLU |
| 2 | 784 (the pixels) | 96 x 784 = 75 264 | sigmoid (a 256-entry table in the FPGA) |

Inputs are bytes: each of the 16 numbers becomes `z x 32 + 128`, and the chosen digit gets `32` (the others 0). Morphing is just giving two digits a share: `32 x (1 - t)` for the 3 and `32 x t` for the 8.

## 3. Two networks in one engine

The engine's memory holds 2048 words per lane. The drawer needs 1218, project 16's reader 800: together 2018, so both stay loaded. Switching between them is 13 register writes (`nn.use()`), so drawing and reading a digit takes well under a millisecond.

# Try it

**Upload and run**: the Monitor shows the bit-for-bit check, each digit drawn and read back, and the speed. Then use the app: Ready projects, Image AI, **Open**.

# Program it

```python
import base64, numpy as np, image_model as im
from blocks import Bus, MLP, mlp_reference
nn = MLP(Bus(), slot=1)
dec = lambda s, shape: np.frombuffer(base64.b64decode(''.join(s)), np.int8).reshape(shape)
drawer = [{'w': dec(getattr(im, 'W%d' % (k + 1)), im.SHAPES[k]), 'b': getattr(im, 'B%d' % (k + 1)),
           'shift': im.SHIFTS[k], 'act': im.ACTS[k]} for k in range(2)]
nn.use(nn.load(drawer))
z = np.random.randn(16)                                   # the style
x = np.concatenate([np.clip(np.round(z * 32) + 128, 0, 255), np.eye(10)[7] * 32]).astype(np.uint8)
_, pixels = nn.run(x)                                     # 784 pixels 0..255: a new 7
```

The registers are the general engine's (see project 17's guide).

# Learn from it

| Idea | Where to see it |
|---|---|
| An autoencoder: squeeze, then draw back | `train()` in `make_model.py`: encoder, decoder |
| The reparameterisation trick | `z = mu + exp(lv / 2) * eps` in `train()` |
| Generation from random numbers | `drawer_input()` in `main.py` |
| Morphing (interpolation) | `/morph` and `/style` in `main.py` |
| Two networks in one accelerator | `nn.load()` twice, `nn.use()` |

## Exercises

1. **Variety.** Draw with variety 0 (all 16 numbers 0): the "average" digit. Then 1, then 2.5. When do the drawings stop looking like digits?
2. **Morph.** Morph 1 into 7, 3 into 8, 4 into 9. Where does the reader change its mind? Is it in the middle?
3. **Fool the reader.** Find a style (seed) where the drawer's digit is read as another digit. What does that picture look like?

<details><summary>What to expect</summary>
Variety 0 gives a clean, average-looking digit; above 2 the strokes break up. The reader usually switches near the middle of a morph, earlier for digits that share strokes (1 and 7). Wrong readings happen with thin or very slanted styles: the drawer is small (96 hidden neurons) and its pictures are a bit blurry.
</details>

# If something is wrong

- **The page in the app says the AI is not running**: press **Upload and run** and wait a few seconds.
- **Blurry digits**: that is how small VAEs draw; more hidden neurons would need more memory than the engine has next to the reader.
- **"The FPGA does not hold the DRAW project"**: upload this project again.
