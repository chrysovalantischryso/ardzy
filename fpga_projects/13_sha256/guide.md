# What it does

This board was made to control a Bitcoin miner: the Antminer S9 sent work to 189 ASIC chips that did nothing but **SHA-256**. This project puts SHA-256 into the board's own FPGA:

- **Hash anything**: the FPGA compresses each 64-byte block of a message; the result equals Python's `hashlib.sha256` to the last bit.
- **Mine like Bitcoin**: give it an 80-byte block header and it tries nonce after nonce, hashing each header twice (double SHA-256), until the hash starts with enough zero bits. It finds the real nonce of Bitcoin block 125552.
- **Race the ARM**: three hashing units side by side do about 1.1 million double hashes per second, many times what Python on the ARM manages.

Nothing to connect. LED 0 blinks while mining, LED 1 lights when a nonce was found.

# How it works

## 1. A hash in one picture

A hash function turns any data into a fixed-size fingerprint (32 bytes for SHA-256). Change one bit of the input and about half the output bits change; there is no way back from the fingerprint to the data, and no shortcut to find data with a chosen fingerprint except trying.

SHA-256 cuts the message into **blocks of 64 bytes** (the last one padded with a 1 bit, zeros and the message length) and runs a **compression** on each block. The compression mixes the block into an 8-word state (H0 .. H7). The state starts with fixed numbers (the square roots of the first 8 primes) and the final state is the hash.

<figure>
<svg viewBox="0 0 860 170" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SHA-256 chains compressions">
<defs><marker id="ah13" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<rect x="10" y="60" width="110" height="50" rx="8" class="d-box"/><text x="65" y="82" class="d-title" text-anchor="middle">IV</text><text x="65" y="100" class="d-small" text-anchor="middle">8 fixed words</text>
<rect x="190" y="50" width="150" height="70" rx="8" class="d-pl"/><text x="265" y="80" class="d-title" text-anchor="middle">compress</text><text x="265" y="100" class="d-small" text-anchor="middle">64 rounds</text>
<rect x="430" y="50" width="150" height="70" rx="8" class="d-pl"/><text x="505" y="80" class="d-title" text-anchor="middle">compress</text><text x="505" y="100" class="d-small" text-anchor="middle">64 rounds</text>
<rect x="680" y="60" width="160" height="50" rx="8" class="d-acc"/><text x="760" y="82" class="d-title" text-anchor="middle">hash</text><text x="760" y="100" class="d-small" text-anchor="middle">H0 .. H7 = 32 bytes</text>
<rect x="190" y="5" width="150" height="30" rx="6" class="d-ps"/><text x="265" y="25" class="d-small" text-anchor="middle">block 1 (64 bytes)</text>
<rect x="430" y="5" width="150" height="30" rx="6" class="d-ps"/><text x="505" y="25" class="d-small" text-anchor="middle">block 2 (+ padding)</text>
<path d="M120 85 H186" class="d-arrow" marker-end="url(#ah13)" color="#b8860b"/><path d="M340 85 H426" class="d-arrow" marker-end="url(#ah13)" color="#b8860b"/><path d="M580 85 H676" class="d-arrow" marker-end="url(#ah13)" color="#b8860b"/>
<path d="M265 35 V46" class="d-line" marker-end="url(#ah13)" color="#888"/><path d="M505 35 V46" class="d-line" marker-end="url(#ah13)" color="#888"/>
<text x="383" y="140" class="d-small" text-anchor="middle">state</text><text x="628" y="140" class="d-small" text-anchor="middle">state</text>
<text x="430" y="163" class="d-small" text-anchor="middle">the state after block 1 is the "midstate": blocks after it only need the midstate, not block 1 again</text>
</svg>
<figcaption>SHA-256 = a chain of compressions, one per 64-byte block.</figcaption>
</figure>

## 2. One round of the compression

Inside a compression, 64 **rounds** each mix one word of the block (W[t]) and one constant (K[t], from the cube roots of the first 64 primes) into eight working words a .. h:

```
T1 = h + S1(e) + Ch(e, f, g) + K[t] + W[t]       S1(e) = e>>>6 ^ e>>>11 ^ e>>>25    Ch = e chooses f or g
T2 = S0(a) + Maj(a, b, c)                         S0(a) = a>>>2 ^ a>>>13 ^ a>>>22    Maj = the majority of a, b, c
h = g   g = f   f = e   e = d + T1   d = c   c = b   b = a   a = T1 + T2
```

`>>>` is a rotation (the bits that fall off the right come back on the left). Only 16 words of W come from the block; W[16] .. W[63] are made from the earlier ones as the rounds go (the **message schedule**). The file `sha256_model.py` has the whole algorithm in 25 lines of Python, the same steps the hardware takes.

## 3. Why a round takes two clocks here

In software a round is a few instructions. In hardware every line above is wires and adders that settle in a certain time. The longest path, `a = h + S1 + Ch + K + W + S0 + Maj`, adds seven 32-bit numbers: about 13 ns in this FPGA, but the clock ticks every 10 ns (100 MHz). The first version of this project did a round per clock and the build tools reported only 75 to 90 MHz: it would have computed wrong hashes.

The fix is a **pipeline stage**: the first clock computes T1, T2 and the next schedule word into registers, the second clock adds them into a .. h. Each half is short, so 100 MHz is easy. A compression now takes 129 clocks (1.29 us).

> **info** This is the most important trade-off in digital design: a shorter path between registers lets the clock run faster, a longer one does more per clock. The build log tells you which one you have: "clock 'clk' 75.4 MHz (FAIL at 100 MHz)" means the longest path is too long.

## 4. Mining

A Bitcoin block header is 80 bytes: version, the previous block's hash, the merkle root (a hash of all transactions), the time, the difficulty ("bits") and a 4-byte **nonce**. Miners change the nonce and compute `SHA-256(SHA-256(header))` until the result, read as a little-endian number, is below the target: in other words it **starts with enough zero bits** when shown the usual way.

<figure>
<svg viewBox="0 0 860 250" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="The miner">
<defs><marker id="bh13" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="currentColor"/></marker></defs>
<rect x="10" y="20" width="200" height="80" rx="8" class="d-ps"/><text x="110" y="45" class="d-title" text-anchor="middle">ARM (Python)</text>
<text x="110" y="65" class="d-small" text-anchor="middle">header bytes 0..63 -&gt; midstate</text><text x="110" y="83" class="d-small" text-anchor="middle">bytes 64..75 -&gt; tail</text>
<path d="M210 60 H266" class="d-arrow" marker-end="url(#bh13)" color="#b8860b"/>
<rect x="270" y="10" width="330" height="230" rx="10" class="d-box"/><text x="435" y="30" class="d-title" text-anchor="middle">FPGA: 3 units side by side</text>
<g><rect x="285" y="42" width="300" height="40" rx="6" class="d-pl"/><text x="300" y="67" class="d-small">unit 0: nonce n    compress(midstate, tail+n) -&gt; compress(IV, ...)</text></g>
<g><rect x="285" y="90" width="300" height="40" rx="6" class="d-pl"/><text x="300" y="115" class="d-small">unit 1: nonce n+1  ...</text></g>
<g><rect x="285" y="138" width="300" height="40" rx="6" class="d-pl"/><text x="300" y="163" class="d-small">unit 2: nonce n+2  ...</text></g>
<path d="M600 134 H656" class="d-arrow" marker-end="url(#bh13)" color="#b8860b"/>
<rect x="660" y="94" width="190" height="80" rx="8" class="d-acc"/><text x="755" y="120" class="d-title" text-anchor="middle">enough zero bits?</text>
<text x="755" y="140" class="d-small" text-anchor="middle">yes: report the first one</text><text x="755" y="158" class="d-small" text-anchor="middle">no: n = n + 3, again</text>
</svg>
<figcaption>The ARM does the part that never changes (the midstate) once; the FPGA does the part that changes with every nonce.</figcaption>
</figure>

Two tricks every miner uses, and this one too:

- **Midstate**: the first 64 header bytes do not depend on the nonce, so their compression is done once (by the ARM). Each nonce then needs only 2 compressions instead of 3.
- **Many units**: units do not need each other, so more units means more hashes. Three units here, about 1.1 million double hashes per second. The S9's 189 chips did 14 thousand billion (14 TH/s); the demo measures how many Python on the ARM manages.

Every extra zero bit doubles the work: 20 bits take about a million tries (under a second here), 32 bits about 4 billion (about an hour). Bitcoin needed about 78 zero bits in 2024.

# Try it

Nothing to wire. **Upload and run**. The Monitor shows:

1. The SHA-256 of a text from the FPGA and from `hashlib`: the same.
2. Bitcoin block 125552: the FPGA searches a million nonces and stops at the block's real nonce, whose hash starts with 16 zero hex digits.
3. A 2-second race on a made-up header: Python on the ARM against the FPGA.
4. Mining for ever on a header that changes its time field: every "block" with 28 zero bits is printed.

# Program it

```python
from blocks import Bus, ShaMiner
import hashlib
sha = ShaMiner(Bus(), slot=1)
print(sha.sha256(b'hello').hex())               # = hashlib.sha256(b'hello').hexdigest()
header = bytes(80)                               # any 80 bytes
r = sha.mine(header, start=0, count=0, zero_bits=20, timeout=10)
print(r['found'], r['nonce'], r['hash'], r['rate'])
```

`mine()` returns `found`, `nonce`, `hash` (shown the Bitcoin way), `hashes` tried, `seconds` and `rate`. `stop()` ends a search, `result()` reads one without waiting.

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | write: [0] start raw [1] start mining [2] stop |
| 1 | STATUS | [0] raw busy [1] mining [2] found [3] finished |
| 2, 3, 4 | NONCE_START, NONCE_COUNT, ZERO_BITS | the search (count 0 = all 2^32) |
| 5, 6, 7 | FOUND_NONCE, HASHES, CYCLES | the result, nonces tried, clocks used |
| 8 .. 15 | MIDSTATE | the state after the header's first 64 bytes |
| 16 .. 18 | TAIL | header bytes 64 .. 75 |
| 24 .. 31, 32 .. 47 | H_IN, BLOCK | raw mode: one compression of any state and block |
| 48 .. 55 | H_OUT | raw mode result |
| 56 .. 63 | FOUND_HASH | the double hash of the nonce found |
| 126, 127 | UNITS, ID | 4, "SHA2" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Pipelining: cut a long path with registers to run the clock faster | `sha256_core`: the first and second half of a round |
| Parallelism: copies of a block work at the same time | `generate for` in `sha_miner`: NU units |
| Precomputing what does not change | the midstate, made once by the ARM |
| Hardware and software sharing a job | `blocks.py ShaMiner.mine()`: Python prepares, the FPGA searches |
| Checking hardware against a model | `selftest.py` and `sim/run_sim.py` compare with `hashlib` |

## Exercises

1. **Count the clocks.** A compression takes 129 clocks, a nonce needs two, and three units work at once. Estimate the hashes per second at 100 MHz, then compare with what the demo prints.

<details><summary>Answer</summary>
Each batch of 3 nonces takes 2 x 129 = 258 clocks plus a few for starting and checking (about 264): 3 / 264 x 100 000 000 = about 1.14 million per second.
</details>

2. **How long for N bits?** On average a hash with N leading zero bits takes 2^N tries. How long does the FPGA need for 24, 28 and 32 bits?

<details><summary>Answer</summary>
2^24 = 16.8 million tries: about 15 s. 2^28: about 4 minutes. 2^32: about 63 minutes (and then all nonces are used: miners change the time or other fields and start again).
</details>

3. **More units.** `top.v` makes 3 units: `sha_miner #(.SLOT(1), .NU(3))`. Change it to 2, **Build FPGA**, upload and run the demo: is it 2/3 of the speed? Then look at the LUT and flip-flop counts in the build log. With 4 units the design needs about 9 500 LUTs and 13 000 flip-flops, and the open-source placer gives up ("unable to find legal placement") even though the chip has 17 600 LUTs: why can a chip be "full" before every LUT is used?

<details><summary>Answer</summary>
A unit is about 2 600 LUTs and 3 600 flip-flops. LUTs and flip-flops are grouped in slices (4 LUTs and 8 flip-flops each), and the flip-flops of one slice must share the same clock enable and reset. Registers with many different enables cannot share slices, so slices run out before LUTs do; the long wires between them also get crowded. Vivado packs more tightly, so it may fit 4.
</details>

4. **Avalanche.** In Python, hash `b'Ardzy'` and `b'Ardzz'` with `sha.sha256()` and count the bits that differ (`bin(a ^ b).count('1')` on the two digests as integers). Why is it close to 128?

<details><summary>Answer</summary>
Each output bit depends on every input bit through 64 rounds of mixing, so a changed input bit flips each output bit with a probability of one half: about 128 of 256 bits.
</details>

5. **One clock per round, done right.** Real miners do a round (or more) per clock. Read `sha256_core`: which additions could be made in the clock before (as `hkw` already is), so that the remaining path fits in 10 ns? (Hint: `d + T1` and `T1 + T2` share T1.)

# Ideas

- Show the hash rate live in the app's Plotter: print `rate:` once a second.
- Make a "proof of work" for your own messages: find a nonce that makes the hash of your text start with 20 zero bits, and let a friend check it with Python.
- Add a SHA-256 stream block to project 11 (AXI-Stream) to hash files as they arrive over the network.

# If something is wrong

- **"The FPGA does not hold the SHA2 project"**: upload this project first (Upload and run).
- **Hashes differ from hashlib**: run the self-test; the simulation test (`python sim/run_sim.py` on the PC, needs Icarus Verilog) shows whether the design or the board is at fault.
- **Mining never finds anything**: each extra zero bit doubles the time; try 20 bits first.
