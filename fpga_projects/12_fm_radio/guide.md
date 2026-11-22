> **warn** **Radio rules first.** Sending radio signals is regulated everywhere. Without a licence you may only use very weak transmitters: in the EU and the UK, small FM transmitters (the kind for a car stereo) may send up to 50 nW e.r.p. in 87.5 to 108 MHz; in the USA, Part 15 allows 250 uV/m at 3 m. Choose a frequency nobody uses where you live, keep the power setting low and the antenna short (10 to 20 cm), and never send on aviation, emergency or other services' frequencies. The Ardzy pin sends a square wave: it also has harmonics (3 and 5 times the frequency). For anything more than a bench test use a filter, or connect an SDR through an attenuator instead of an antenna. You are responsible for what you send.

# What it does

This project turns one FPGA pin (J9 pin 11) into a complete radio station:

- **FM stereo** (WFM) with the 19 kHz pilot, so receivers light their "stereo" lamp
- **RDS**: your station name (8 characters), a radio text of up to 64 characters (it can show the song that is playing), the programme type (Pop, Rock, News ...), the clock time (car radios set their clock from it), traffic flags and other frequencies
- **NFM** (narrow FM, like walkie-talkies), **AM**, **USB**, **LSB** and **DSB** for scanners, short-wave receivers and SDRs
- **sound** from four sources: test tones, songs (WAV files on the board, in a playlist), **pictures** (SSTV) and live **network sound** (AES67)
- **digital modes**: Morse code (CW), radio teletype (RTTY), PSK31 / 63 / 125 / 250, slow Morse for waterfalls (QRSS, DFCW), Hellschreiber, the WSPR beacon, a melody beacon and frequency sweeps
- **a picture in the waterfall** of an SDR program (SDR#, SDR++, HDSDR, a WebSDR): your image or your text, up to 28 kHz wide
- **radiofax** (WEFAX) pictures, **APRS** packets (AX.25, 1200 baud) and **DTMF** key tones

| Mode | What a receiver needs | How it is made |
|---|---|---|
| WFM | any FM radio | the stereo multiplex moves the carrier frequency, up to 75 kHz |
| NFM | a scanner or an SDR in NFM | the voice band (300 to 2700 Hz) moves the frequency, 2.5 or 5 kHz |
| AM | an AM radio, SDR in AM | the sound changes the carrier's strength |
| USB, LSB | a short-wave receiver, SDR in USB / LSB | only one side band, no carrier: strength and phase from I and Q |
| DSB | SDR in DSB (or USB / LSB) | both side bands, no carrier |
| CW, RTTY, PSK31 .. PSK250, Hell | SDR in CW / USB, fldigi for RTTY, PSK and Hell | the symbol player |
| QRSS, DFCW | a slow waterfall (Argo, Spectrum Lab, SDR#) | the symbol player, dots of seconds |
| WSPR | WSJT-X (USB) | the symbol player: 4 tones 1.46 Hz apart, 110.6 s, every even minute |
| Picture in the waterfall | SDR#, SDR++, any waterfall | I / Q made on the ARM: one tone per column |
| Radiofax | fldigi (WEFAX), HamFax, SDR# plugins | sound made on the ARM, sent in USB or NFM |
| APRS, DTMF | Direwolf, multimon-ng, APRSdroid; a scanner | sound made on the ARM, sent in NFM |

(Your SDR also offers **RAW**: that only shows the raw I / Q of what it receives; there is nothing to send for it.)

Everything is made inside the FPGA. The ARM only writes settings, sound samples and RDS data. In the Ardzy app open **Ready projects** and press **Open** on the FM radio card: that is the station's control page. This guide explains how it all works.

# How the signal is made

## 1. A carrier from a counter

A 32-bit number, the **phase**, grows by a step every sample. When it passes 2^32 it starts again from 0: one turn of the carrier. The pin is high while the phase is in the first half of the turn. A bigger step gives a higher frequency:

```
frequency = step * 500 MHz / 2^32        (steps of 0.116 Hz)
96.0 MHz  ->  step = 824 633 721
```

The FPGA cannot toggle a pin 500 million times per second with ordinary logic, so it uses two tricks: a 250 MHz clock made by the MMCM (the clock multiplier: 100 MHz x 10 / 4), and an **ODDR**, a flip-flop in the pin itself that sends one value on the rising edge of the clock and another on the falling edge. Two samples per clock: 500 million per second. Carriers up to about 200 MHz are possible; the counter that measures the pin reaches 125 MHz.

The adders run at 250 MHz, so they are split: each 32-bit sum is made of two 16-bit halves, with the carry passed on one clock later. The result is exactly the same number, just a few clocks later.

## 2. FM: the stereo multiplex (MPX)

FM moves the carrier frequency with the sound. For stereo, the sound is first packed into one signal, the **multiplex** (MPX), 390625 samples per second:

| Part | Where | What it is |
|---|---|---|
| L+R | 30 Hz to 15 kHz | left plus right: what a mono radio plays |
| pilot | 19 kHz | a quiet tone that says "this is stereo" (9 %) |
| L-R | 23 to 53 kHz | left minus right, on a 38 kHz carrier that is then removed (DSB-SC) |
| RDS | 54.6 to 59.4 kHz | the data, on 57 kHz (3 x 19) |

A stereo radio locks to the 19 kHz pilot, doubles it to 38 kHz, gets L-R back, and makes L = (L+R) + (L-R) and R = (L+R) - (L-R). All the parts use one phase counter, so 19, 38 and 57 kHz stay exactly in step.

The sound path in the FPGA, one stage after the other:

1. **resampler**: songs come at any rate (44.1 kHz, 48 kHz ...); the FPGA takes them at that rate and turns them into 48828 samples per second (linear interpolation)
2. **volume**, then **pre-emphasis**: the highs are made louder (50 us in Europe, 75 us in the Americas); the radio makes them quieter again and the hiss goes down with them
3. **15 kHz low-pass**, 63 taps: nothing may reach the 19 kHz pilot (19.5 kHz is blocked by more than 80 dB)
4. **M and S**: M = (L+R)/2, S = (L-R)/2
5. **x8 interpolation**, 96 taps: from 48828 to 390625 samples per second without mirror images
6. **the sum**: 87 % sound, 9 % pilot, 4 % RDS, then the deviation: 75 kHz at full MPX

## 3. RDS

RDS sends 1187.5 bits per second (19 kHz / 16). The data comes in **groups** of 4 blocks; each block has 16 data bits and a 10-bit check word that also marks which block it is, so a receiver finds the start and corrects errors.

| Group | Carries |
|---|---|
| 0A | 2 characters of the station name (PS) per group, the PTY, TP, TA and music / speech flags, other frequencies |
| 2A | 4 characters of the radio text (RT) per group, and the A/B flag that flips for a new text |
| 1A | the extended country code (ECC): with the first digit of the PI it names the country |
| 3A + 11A | RT+ (RadioText Plus): which part of the text is the title and which the artist, so car radios can show them apart |
| 10A | the programme type name (PTYN): 8 characters of your own, for example "House" |
| 4A | the date and the time (UTC and the local offset), once a minute; only when the board's clock is known to be right (network time, or the Ardzy app set it), because the board has no battery clock |

The ARM (rds.py) builds the groups and writes them into one of two **banks** in the FPGA. The FPGA sends a bank round after round; when the ARM has filled the other bank and asks for it, the change happens at the end of a round, so a receiver never sees half a group. Both banks share one length register, so rds.py always keeps them the same length: a shorter round is padded with its own groups and the bank on air is extended with its own groups before a longer one is asked for. That way a round is never cut short and no old block from an earlier round can slip on air. Each bit is sent differentially coded (a 1 flips the level) and as one smooth sine period (biphase), which keeps the RDS signal narrow and leaves no carrier at 57 kHz.

## 4. NFM, AM, SSB and DSB

**NFM** is FM with a small deviation (5 kHz) and only the voice band. The FPGA's voice filter is the same 256-tap filter the side band modes use; it passes 300 to 2700 Hz and is mono.

**AM** and the **power** setting change the strength, see below.

**USB / LSB** (single side band) sends only one half of what AM sends, without the carrier: half the width and all the power in the sound. The classic way to make it is the phasing method: from the sound make two copies 90 degrees apart, **I** and **Q** (Q is the Hilbert transform of I), and then

```
USB = I x cos(carrier) - Q x sin(carrier)       LSB: Q with the other sign
```

The FPGA makes I and Q with one complex filter of 256 taps (a 1200 Hz low-pass moved up to 1500 Hz): 32 taps in each of the 8 MPX samples of an audio sample, so it fits in the time. The other side band is about 70 dB down (computed from the stored coefficients) and measured more than 40 dB down in the self-test. A pin can only be high or low, so the signal is made in **polar** form: a small CORDIC (14 shift-and-add steps) turns I and Q into a **strength** (the pulse width, through the same table as AM) and a **phase** (added to the carrier's phase), 390625 times a second. **DSB** is the same with Q = 0: the strength follows the size of the sound and the phase turns by half a turn when the sound changes sign.

The strength is made from pulses of whole 2 ns samples, so these modes are cleanest on medium and short wave (below about 30 MHz), where a period has many samples.

**I/Q** (mode 8) uses the same CORDIC, but I and Q come straight from the ARM: the left sample of the sound FIFO is I, the right one is Q. They pass the 15 kHz low-pass (so the signal can use about +-14 kHz around the carrier) and the x8 interpolation. With it the ARM can make any signal: the radio uses it to paint pictures into an SDR's waterfall. Writing the rate register (RATIO) puts the resampler on a whole sample, so at the FPGA's own rate (48828.125 per second) the samples pass unchanged: the self-test measures the other side 106 dB down and no tilt between 2 and 12 kHz.

## 5. The strength (AM, power) and the digital modes

The strength of the pin's square wave depends on how long it is high in each turn: half a turn gives the strongest carrier, shorter pulses a weaker one (the strength is sin(pi x width)). **AM** changes the width with the sound (through a small table, so the strength follows the sound in a straight line). The **power** setting uses the same idea.

A pulse cannot be shorter than one sample (2 ns). At 96 MHz a period is only about 5 samples, so the weakest clean setting there is about 57 %: the service never goes lower (the page shows it) because shorter pulses would come and go irregularly and make spurious signals. For less power at FM frequencies use a resistor in series with the antenna, or a shorter antenna. On short wave (a few MHz) the power can go almost to zero.

The FPGA measures this at the pin: it counts the time the pin is high (RF_HIGH). The self-test checks the power setting and AM against the formula at 6.78 MHz, after it has measured the pad's own edge timing (its rise and fall differ by about 2 ns).

The **symbol player** takes a list of steps, each one: a frequency offset, a time in microseconds, a strength and a phase. That is enough for:

- **CW**: carrier on and off, with soft edges (4 ms) so the signal stays narrow
- **RTTY**: two tones 170 Hz apart, 45.45 bits per second, the 5-bit Baudot code
- **PSK31**: 31.25 bits per second; a 0 turns the phase by half a turn, the strength goes through zero while it does. **PSK63, PSK125, PSK250**: the same, 2, 4 and 8 times faster (and that much wider)
- **QRSS**: Morse with a dot of 3, 10 or more seconds, so slow that it is read on a waterfall, far below the noise you could hear. **DFCW**: dots and dashes are the same length, a dash a few Hz higher
- **Hellschreiber** (Feld Hell): each letter is scanned like a fax, 7 columns of 14 dots from the bottom up, 122.5 dots a second (0.8 s a letter); the carrier is on for ink. fldigi draws the letters, and a slow waterfall shows them too
- **WSPR**: your call sign, a 4-character locator and the power in dBm, packed into 50 bits, protected by a convolutional code (K = 32) and spread over 162 symbols of 4 tones, 1.46 Hz apart, 0.683 s each (110.6 s). It starts 1 s after an even minute, so the board's clock must be right (the app sets it). WSJT-X decodes it down to -28 dB below the noise. The encoder is checked against another program's output for 4 messages
- **beacon**: a melody: each note is a carrier offset, so an SSB receiver plays it as a tone
- **sweep**: the carrier steps across a range (to measure a filter or an antenna)

# Try it

1. Choose a free frequency. In the FM band, listen with a radio first: between two stations is not enough, the place must be silent.
2. Wire a 10 to 20 cm wire to J9 pin 11 (or nothing at all for the first test: the pin and its track radiate a little).
3. In the Ardzy app open **Ready projects**, the FM radio card, **Open** (press **Start the radio on the board** if it is not running yet).
4. Set the frequency, keep the power low, press **OFF AIR** so it says **ON AIR**. The test tones play: 1000 Hz on the left, 400 Hz on the right.
5. Tune your radio to the frequency. The station name appears after a second or two, the radio text a few seconds later.
6. **Songs**: press **Send a WAV file**. When it has arrived it joins the playlist. The radio text can show the song: write `{title}` in it.
7. **Pictures**: choose **Picture**, pick any image (it is fitted to 320 x 256; you can write a call sign on it), choose the SSTV mode and press **Send this picture**.
8. **Network sound**: choose **Network**; streams announced on the network appear in the list, or type an address and port.
9. **A picture in the waterfall**: choose the mode **Picture in the waterfall**, pick an image (or type a text), choose ready settings, press **Send to the waterfall** and go on air. See the next chapters for the speed and the SDR settings.

# The studio console (in the app)

The radio page is laid out like a broadcast desk (always dark, like a studio):

- **ON AIR lamp** (press it to go on or off air), the frequency in LED digits (red on air), the tuning buttons, the mode and the power.
- **Status lamps**: ON AIR, CARRIER (seen at the pin), PLL (the 250 MHz clock locked), STEREO, RDS (decoded on the board), TA, AUDIO, CLIP, NET (network sound arriving), DELAY (blue when set, amber while it fills), GAPS (red for 5 s after a gap in the sound).
- **Studio clock**: the PC's time with a ring of 60 seconds.
- **Timers**: how long the station has been on air; the song's elapsed and remaining time (amber in the last 20 s, red and blinking in the last 10 s; LIVE for network sound and test tones); the next song; the time to the top of the hour; when the RDS name and text change next; a stopwatch; a countdown you set (minutes:seconds).
- **Meter bridge**: LED peak meters with a 2 s peak hold for the sound coming in, going out of the processing and on air in the FPGA (after pre-emphasis), the MPX in % of the deviation (100 % = full deviation) and GR, how much the limiter turns the sound down.
- **Stereo image**: a goniometer (a vertical line is mono, a wide cloud is wide stereo, a horizontal line is left and right in opposite phase, which would cancel on a mono radio) and the correlation meter (+1 mono, 0 unrelated, below 0 a phase problem).
- **Real-time analyzer**: the sound after the processing in 31 third-octave bands (20 Hz to 20 kHz) with peak markers; the blue line is the sound before the processing.
- **MPX spectrum and waterfall**: the signal that moves the carrier, 0 to 80 kHz: L+R, the 19 kHz pilot (its level is shown), L-R around 38 kHz and RDS at 57 kHz, with an amber peak trace and a waterfall of the last minute. Live, it asks the board for a capture about once a second; that never touches the settings or the sound.

# Sound in and out (buffer, processing, delay)

Every sound that is not a test tone (songs, pictures, network sound) passes the same chain on the board before the FPGA gets it:

**source** -> resampled to 48 kHz -> **gain, balance, mono, swap** -> **AGC** (an automatic level) -> **limiter** (never above the ceiling) -> **delay** -> the FPGA's buffer -> pre-emphasis -> FM -> the pin.

The **Sound in and out** card in the app shows this flow with live meters: the level before and after the processing (peak and average, with a peak hold), a 20 ms waveform of each, the levels on air in the FPGA, the last 30 s as a graph, how much the limiter works, the delay right now and a **click counter**.

- **Buffer** (network sound, 20 to 2000 ms, 150 ms by default): the sound kept in hand against late packets. Clicks come from a buffer that runs dry, so if you hear any, make it bigger: 300 ms rides out almost any network hiccup. A change takes effect at once (a moment of silence or a short skip). The board then follows the sender's clock by nudging its own rate by a few hundred ppm, so the buffer stays where you set it for hours.
- **Clicks**: counts gaps in the sound while a source is really playing (not between songs, before a stream or while the delay fills). It should stay at "none".
- **Gain / Balance / Mono / Swap**: the usual. **AGC** brings quiet sound up and loud sound down, slowly, towards its target. **Limiter**: nothing goes above the ceiling, so the station never over-modulates. **Bypass** sends the sound as it comes.
- **Delay** (0 to 10 s): the whole programme is heard later, for example to match a video stream. The radio text follows: a new song shows up in RDS when it is heard, not when it starts in the delay line. When the sound stops, what is still in the delay plays out to its end.

An MPX capture (the spectrum in the app) runs beside the sound and does not disturb it.

# Pictures (SSTV)

Slow-scan television sends a picture as sound: the pitch is the brightness, from 1500 Hz (black) to 2300 Hz (white); a 1200 Hz pulse starts every line, and before the picture the **VIS code** (0.9 s of tones) tells the receiver the mode.

| Mode | Picture | Time | Colours |
|---|---|---|---|
| Martin 1 | 320 x 256 | 114 s | green, blue, red per line |
| Scottie 1 | 320 x 256 | 110 s | green, blue, then the sync, then red |
| Robot 36 | 320 x 240 | 36 s | brightness, and every other line one colour difference |
| Martin 2 | 320 x 256 | 58 s | as Martin 1, twice as fast |
| Scottie 2 | 320 x 256 | 72 s | as Scottie 1, faster |
| Scottie DX | 320 x 256 | 270 s | as Scottie 1, slow: the best for weak signals |
| PD 90 | 320 x 256 | 90 s | brightness of two lines with their shared colour differences |

The board makes the sound (with numpy, in about a second) and plays it like a song, so a picture works in **every sound mode**: FM for a phone next to a radio (the free app **Robot36** decodes it from the speaker), USB / LSB on short wave for MMSSTV or QSSTV. A test checks the sound itself: the VIS codes and the pixels measured from the pitch come back within 1 of 255.

# A picture in the waterfall (SDR#, SDR++)

An SDR program draws the spectrum as a **waterfall**: many times a second a new line of colour, one dot for each small slice of frequency, brighter where the signal is stronger, and the old lines move down. If the radio sends many tones side by side, one for each column of a picture, each as strong as its pixel is bright, and then the next line of the picture, and so on, the waterfall draws the picture.

```
column k of the picture   ->  a tone at  low end + k x spacing      (spacing = width / (columns - 1))
brightness of the pixel   ->  the strength of that tone, in dB (white = 0 dB, black = silent)
each line of the picture  ->  "Speed" milliseconds, then the next line
```

**How the board makes it.** The tones sit on a grid of 5.96 Hz (the FPGA's sound rate 48828.125 divided by 8192). One inverse FFT of 8192 points per line gives a block of samples that repeats without a seam, so every tone keeps its phase from line to line: no clicks, sharp columns. Between two lines the strengths change over a few milliseconds ("Soft edges"), so the lines do not splash across the spectrum. The tones start with Newman phases (pi k^2 / n), which keeps the peaks low, and the whole picture is scaled once from its loudest line, so the same grey is the same strength in every line. On the PC test, every lit pixel comes back within 1.5 dB of its brightness, black stays more than 70 dB down and nothing appears outside the picture.

**Two ways to send it:**

| Send as | Width | Needs | Receiver |
|---|---|---|---|
| **I/Q** (best) | up to 28 kHz, centred on the frequency (or beside it, "Centre") | the I/Q mode of this design (any 12_fm_radio built from November 2026 on) | any mode: the picture is there whatever the demodulator |
| **USB** | 300 to 2700 Hz above the frequency | nothing (every design) | the RF waterfall, or a USB receiver's audio waterfall, a WebSDR |

## The settings

| Setting | What it does | Good values |
|---|---|---|
| **Picture / Text / Test picture** | an image file, a text you type (drawn in big bold letters), or the test picture (frame, diagonal, grey ramp, ARDZY) | text is the easiest to read |
| **Ready settings** | fills in width, columns, speed and contrast for a typical receiver | start here |
| **Width** | how wide the picture is on air | 20 to 26 kHz (I/Q), 2.4 kHz (USB) |
| **Centre** | where the middle of the picture is, from the frequency | 0; move it to keep clear of a signal |
| **Columns** | how many tones: the picture's sharpness across | 100 to 256 |
| **Line height** | how many lines the picture gets for its shape (x1 = as it is) | 1; less for a quicker picture |
| **Speed** | the time of one line | 30 to 80 ms (see below) |
| **Contrast** | how far below white the darkest grey that is still sent lies | 30 dB; 40 dB with a strong signal |
| **Black level** | pixels darker than this are not sent at all (a clean black background) | 5 to 10 % |
| **Gamma** | more than 1 makes the middle greys darker, less than 1 lighter | 1 |
| **Stretch the greys** | the darkest pixel black, the brightest white | on for photos |
| **Negative**, **Mirror** | white and black swapped; left and right swapped (for a receiver in LSB) | off |
| **Bottom line first** | waterfalls scroll down, so the line sent first ends at the bottom: the picture is sent from its bottom line up and stands upright | on (off for a waterfall that scrolls up) |
| **Soft edges** | the time the strengths take to change between lines | 3 to 5 ms |
| **Repeat** | send it again after these seconds | 0 = once |

The page shows the picture as it is sent and **how a waterfall will show it** (with a waterfall's colours and noise), the frequencies it covers on air, the spacing of the tones and how long it takes.

## Speed and size: the numbers that matter

A waterfall is made of FFTs. Two numbers of your SDR program decide what it can show:

- **FFT bin** = the receiver's sample rate / the FFT size. An RTL-SDR at 2.4 MS/s with an FFT of 65536 points: 36.6 Hz.
- **FFT time** = the FFT size / the sample rate: 65536 / 2.4 MS/s = 27 ms. One waterfall line is at least that long.

For a sharp picture:

1. **Columns at least 2.5 to 3 bins apart.** 20 kHz / 128 columns = 157 Hz = 4.3 bins: sharp. 20 kHz / 400 columns = 50 Hz = 1.4 bins: the columns melt together. More columns need more width or a bigger FFT.
2. **A line at least one FFT long, better two.** With 27 ms FFTs, 30 ms lines are the least, 50 to 80 ms are clear. Quicker lines blur into each other.
3. **The picture takes lines x speed.** 128 x 96 lines at 40 ms = 3.8 s; 256 x 192 at 60 ms = 11.5 s.

The card's "Your SDR program" part does this arithmetic for your receiver's rate and FFT size and says "sharp" / "clear" or what to change.

**The shape.** On the screen a column is (spacing / Hz per screen pixel) wide and a line is (speed x waterfall lines per second) tall, and both depend on the zoom and the waterfall speed of your program. If the picture comes out **flat** (squashed), make the lines slower (more ms) or the waterfall slower; if it is **too tall**, the other way round, or lower "Line height". Text is forgiving: it reads well squashed or stretched.

| Ready setting | Width | Columns | Speed | A 4:3 picture takes |
|---|---|---|---|---|
| SDR# / SDR++ quick | 20 kHz | 128 | 30 ms | 2.9 s |
| SDR# / SDR++ detailed | 24 kHz | 200 | 50 ms | 7.5 s |
| SDR# / SDR++ big and slow | 26 kHz | 256 | 80 ms | 15 s |
| Narrow, for a small zoom | 8 kHz | 64 | 60 ms | 2.9 s |
| A receiver in USB (audio waterfall) | 2.4 kHz | 64 | 100 ms | 4.8 s |
| WebSDR / slow waterfall | 2 kHz | 40 | 400 ms | 12 s |

## SDR# step by step

1. Wire the board to the SDR the safe way: J9 pin 11 through a 1 kohm resistor and a 30 to 40 dB attenuator to the SDR's input, pin 1 (GND) to the cable's outer conductor. Not an antenna.
2. In the radio page choose a **free frequency** the SDR can receive (an RTL-SDR from 24 MHz up; below that only in direct sampling mode, which RTL-SDR V3 / V4 sticks have). Short wave gives the cleanest picture (each carrier period has many 2 ns samples), but 27 to 150 MHz works too. Keep the power low.
3. Choose **Picture in the waterfall**, a picture or a text, the ready setting **SDR# quick**, press **Send to the waterfall**, then **OFF AIR** so it says **ON AIR**.
4. In SDR#: tune to the frequency (the centre of the picture is the frequency plus "Centre"). Any demodulator mode will do (the picture is in the RF spectrum); NFM or USB with the volume down.
5. **FFT Display**: Resolution 65536 (or 32768), Window Blackman-Harris 4, View Both or Waterfall. **Zoom** in until the picture covers about half the screen (about 40 to 50 kHz across for a 20 kHz picture).
6. **Speed** (the waterfall speed) to the top. **Contrast / Range / Offset**: a range of about 40 dB, the noise just dark.
7. Watch the picture scroll in. Adjust "Speed" in the radio page for the shape, the attenuator or the SDR's gain if it is too strong (it splashes) or too weak.

**SDR++**: Display: FFT size 65536, FFT window Blackman-Harris, waterfall speed up; zoom with the slider at the left of the spectrum; min and max of the waterfall about 40 dB apart. **HDSDR** and **GQRX** work the same way (FFT resolution, speed, range). **WebSDR** and receivers listening by ear: use **USB** with 2 kHz and slow lines: the audio waterfall of the receiver draws it.

**Harmonics**: the pin sends a square wave, so the picture also appears at 3 and 5 times the frequency (weaker, and 3 or 5 times wider). That is one more reason to test into an SDR through an attenuator and not to send it over the air.

# Radiofax (WEFAX)

Weather services still send maps on short wave this way. A grey picture goes line by line as a tone: 1500 Hz is black, 2300 Hz white, **120 lines a minute** (0.5 s a line), each line 1810 dots wide (pi x the **IOC** 576). Before the picture: 5 s of the start tone (black and white in turn 300 times a second, which tells a receiver "IOC 576, start"), then **phasing** lines (black with a white pulse at the line start, so the receiver finds where a line begins), then the picture, the stop tone (450 Hz, 5 s) and 10 s of black. Choose a picture in the **Radiofax** card (it is sent 905 dots wide and stretched to 1810), the speed (60, 90, 120 or 240 lines a minute), and **Send this picture**. Receive with **fldigi** (Op Mode, WEFAX, WEFAX-576) or HamFax, the receiver in USB 1.9 kHz below the frequency (that puts 1500 to 2300 Hz in its sound). In NFM it works with any FM receiver feeding the sound to fldigi.

# APRS packets and DTMF

**APRS** sends short text messages and positions as AX.25 packets: 1200 bits a second as two tones (1200 Hz and 2200 Hz, Bell 202), a change of tone for a 0 bit (NRZI), flags at both ends, a 0 stuffed after five 1s, and a CRC at the end. The board makes the sound and sends it in NFM (3 kHz deviation). Fill in your call sign (with an SSID: -9 for a car, -7 for a handheld), the path (WIDE1-1), the text or a position (latitude, longitude). Decode with **Direwolf**, **multimon-ng** (`-a AFSK1200`), an SDR# / SDR++ packet plugin or the phone app **APRSdroid** with a radio. The PC test decodes the tones back to the frame and checks the CRC. APRS frequencies (144.800 MHz in Europe, 144.390 MHz in North America) belong to licensed radio amateurs: test on a free frequency into an SDR.

**DTMF** are telephone key tones: each key is two tones at once (a row 697, 770, 852 or 941 Hz, and a column 1209, 1336, 1477 or 1633 Hz), 100 ms each with 100 ms between (both can be set). Type the keys (0-9, *, #, A-D; a space is a pause). Decode with multimon-ng (`-a DTMF`) or listen with a scanner in NFM.


# Network sound (AES67)

**AES67** is the standard for uncompressed sound over a network: studio consoles and RAVENNA devices, Dante devices in AES67 mode, PipeWire on Linux and ffmpeg all speak it. The sound goes in RTP packets over UDP, usually to a multicast address (239.x.x.x, port 5004): 48 kHz, 24 bit (L24) or 16 bit (L16), 1 ms per packet. Senders announce their streams with **SAP** (a short SDP text with the name, address and format).

The radio service listens to SAP and lists the streams it hears; choose one, or type the address, port and format. It collects the buffer (150 ms unless you choose another size), then plays, and keeps the buffer at that size by nudging the FPGA's resampler by up to 0.4 %: the level is smoothed over a second, a proportional part pulls it back within about 10 s and a slow integral part learns the real difference between the two clocks, so the buffer settles without swinging and never runs dry or over. (AES67 devices also share a PTP clock; a receiver like this one just follows the stream's own pace, which is all a radio needs.) The stream is also received with the transmitter off, so the meters show it before you go on air.

## The easy way: from the Ardzy app

On the radio's page choose **Network**, then under **From this PC**:

- **Send this PC's sound**: pick "Everything this PC plays on: ..." (your speakers, or VB-CABLE if Windows plays into it) or an input (a microphone). The app takes the sound with Windows' own audio interface (WASAPI) and sends it as AES67 (L24, 1 ms packets) **straight to the board**, over the same cable the app already talks to it on.
- **AES67 streams this PC hears**: any AES67 program on this PC, or a device on another network this PC is on, that announces itself (SAP) appears in this list; **pass on to the radio** relays it to the board the same way.

Why this matters: an AES67 program sends multicast out of **one** network card. With two cards (the internet one with the default route, and the cable to the board), Windows usually picks the internet card, and the board never sees the stream. Sending straight to the board, or relaying, makes the choice of card irrelevant. A new sender (another program, a restart) is followed at once: the board watches the sender's id (SSRC) and starts counting its packets anew.

## Other senders

From this PC, without the app:

```
python aes67_send.py song.wav                  (in the project folder: a WAV file, over and over)
python aes67_send.py --tone 1000 --name "Test"
```

Live sound from the PC (a microphone, or everything the PC plays through a virtual cable such as VB-CABLE) with ffmpeg; then type 239.69.83.67, port 5004, L24, 48000, 2 on the page:

```
ffmpeg -f dshow -i audio="CABLE Output (VB-Audio Virtual Cable)" -ac 2 -ar 48000 -c:a pcm_s24be -payload_type 96 -f rtp "rtp://239.69.83.67:5004?localaddr=192.168.137.1&pkt_size=300"
```

(`localaddr` is this PC's address on the cable to the board.) With PipeWire on Linux, load the AES67 module; Dante devices need AES67 mode switched on in Dante Controller.

The **What radios show** box is decoded on the board from the bits the FPGA really sent, the way a car radio does it. The **MPX signal** card captures 4096 samples inside the FPGA and draws their spectrum: you can see the sound, the pilot, the stereo part and RDS.

## Listening with an SDR

An RTL-SDR stick with SDR# or SDR++ shows everything: the FM signal and its RDS (WFM mode, RDS on), NFM, the AM carrier and its side bands, USB / LSB / DSB voice, the CW and RTTY tones (USB mode). Connect the pin through a 1 kohm resistor and a 30 to 40 dB attenuator to the SDR input, never directly. For RTTY and PSK31 run **fldigi**: set the SDR to USB about 1 kHz below the frequency and send its sound to fldigi (a virtual audio cable).

# Program it

The radio's control page writes `radio.json` on the board; the radio service (main.py) does the rest. You can also use the block directly from Python:

```python
from blocks import Bus, Radio
import rds, modes

r = Radio(Bus(), slot=1)
r.frequency(96.0e6)
r.power(0.2)                         # 20 % strength
r.setup(tx=True, stereo=True, rds=True, preemph=50, tones=True)
r.tones(1000, 400)
r.mode('fm')

st = rds.Station(pi=0x1A2D, ps='MY RADIO', rt='Hello from the FPGA', pty=10)
r.rds_load(st.cycle(), bank=1)       # the FPGA changes to bank 1 at the end of the round

r.mode('symbols')                    # Morse code at 20 words per minute
r.send(modes.cw('CQ CQ DE ARDZY', wpm=20))
```

Other helpers: `r.mode('usb')` (or `'lsb'`, `'dsb'`), `r.setup(narrow=True)` (the voice filter: NFM, narrow AM), `r.input_rate(44100)` and `r.push(words)` for your own sound (8192 places), `r.capture()` for 4096 MPX samples, `r.capture_iq()` for 2048 I / Q pairs, `r.peaks()`, `r.rf_hz()` (the carrier counted at the pin), `r.rf_duty()` (the time the pin is high), `rds.decode(r.rds_log())` to read back what was sent, `modes.rtty()`, `modes.psk31(text, baud=62.5)`, `modes.qrss()`, `modes.hell()`, `modes.wspr(call, locator, dbm)`, `modes.beacon()`, `modes.sweep()`, `sstv.audio_words(rgb, 'martin1')`, `aes67.Receiver(r, '239.69.83.67', 5004)`.

Your own I / Q signal (for example a picture):

```python
import paint
r.mode('iq')
r.setup(tx=True, tones=False, preemph=0, stereo=False)
r.input_rate(r.FS_AUDIO)                       # 48828.125: no resampling
p = paint.Painter(paint.read_pgm('my.pgm'), {'width_hz': 20000, 'line_ms': 40}).start()
for words in p.words():                        # FIFO words: Q << 16 | I
    while r.audio_free() < len(words):
        time.sleep(0.01)
    r.push(words.tolist())
```

## The radio service (radio.json)

| Key | Meaning |
|---|---|
| `on`, `mode`, `freq_mhz`, `power` | the transmitter: mode fm, nfm, am, usb, lsb, dsb, carrier, cw, rtty, psk31, psk63, psk125, psk250, qrss, hell, wspr, beacon, sweep, paint, wefax, aprs or dtmf |
| `audio.source` | tones, playlist, sstv, network or silence; `audio.playlist`, `loop`, `shuffle`, `volume`, `tone_l`, `tone_r` |
| `nfm`, `am` | `nfm.deviation_khz`; `am.depth`, `am.voice` (the voice filter) |
| `sstv` | `mode` (martin1, martin2, scottie1, scottie2, scottiedx, robot36, pd90), `image` (320 x 256 RGB bytes), `repeat_s`, `id` (change it to send again) |
| `paint` | the picture in the waterfall: `image` (a grey PGM), `kind` (iq, usb), `width_hz`, `offset_hz`, `line_ms`, `contrast_db`, `black`, `gamma`, `invert`, `mirror`, `bottom_first`, `edge_ms`, `level`, `repeat_s`, `id` |
| `wefax` | `image` (a grey PGM), `lpm` (60, 90, 120, 240), `ioc` (576, 288), `phasing_s`, `via` (usb, fm), `repeat_s`, `id` |
| `packet` | APRS: `call`, `dest`, `path`, `text`, `position`, `lat`, `lon`, `symbol`, `deviation_khz`, `repeat_s`, `id` |
| `dtmf` | `digits`, `tone_ms`, `gap_ms`, `deviation_khz`, `repeat_s`, `id` |
| `network` | `stream` (address:port of an announced stream) or `address`, `port`, `encoding` (L24, L16), `rate`, `channels`, `buffer_ms`, `label` |
| `process` | `gain_db`, `balance` (-1..1), `mono`, `swap`, `agc`, `agc_target_db`, `limiter`, `ceiling_db`, `bypass` |
| `delay_s` | the delay of the programme, 0 to 10 s |
| `rds` | `ps`, `rt`, `pi`, `pty`, `tp`, `ta`, `music`, `ct`, `af`, `ptyn`, `ecc` (2 hex digits), `rtplus` |
| `rds.ps_mode` | `fixed` (`ps`), `list` (`ps_list`: names with their seconds), `scroll` or `words` (`scroll` text, `scroll_s` per step) |
| `rds.rt_list` | a loop of texts, each with its seconds; empty: the one text `rt` |
| `fm` | `stereo`, `preemph` (50, 75, 0), `deviation_khz`, `audio`, `pilot`, `rds_level` (shares, 0..1) |
| `digital` | `text`, `wpm`, `baud`, `shift`, `offset_hz`, `melody`, `tempo`, `sweep_...`, `qrss_dot_s`, `dfcw_hz`, `hell_wide`, `wspr_call`, `wspr_locator`, `wspr_dbm`, `wspr_every_min`, `repeat_s`, `id` (change it to send again) |
| `delete` | files to remove from the project folder (songs .wav, pictures .pgm) |

The service writes `status.json` twice a second: the carrier counted at the pin, the time it is high, the power used, the level meters, the song or picture and its position, what RDS receivers decode, the network streams and the receiver (packets, losses, buffer, clock follow), gaps in the sound. A thread of its own keeps the sound and the symbols flowing every 5 ms.

### RDS texts: lists, loops and variables

The station name can be fixed, a **list** of names (each shown for its own seconds), a **scrolling** text or a text shown **word by word**. The radio text can be one text or a **loop** of texts. Both can use variables, filled in on the board and updated when they change: `{title}`, `{artist}`, `{song}` (artist - title), `{time}`, `{date}`, `{freq}`, `{station}`. The app shows a preview of what goes on air and what receivers decode. Note that many car radios ignore a station name that changes quickly; a list with 4 s or more per name is the friendly way.

## Registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] transmit [1] stereo [2] RDS [3] pilot [5:4] pre-emphasis [6] mute [7] test tones [8] voice filter |
| 1 | MODE | 0 off, 1 carrier, 2 FM, 3 AM, 4 symbols, 5 USB, 6 LSB, 7 DSB, 8 I/Q (left = I, right = Q); an older design reads 8 back as 0 |
| 2 | FREQ | carrier = FREQ x 500 MHz / 2^32 |
| 3 | DEV | deviation at full MPX, 1288530 = 75 kHz |
| 4..6 | G_AUDIO, G_PILOT, G_RDS | shares of the MPX, Q15 |
| 7 | VOLUME | 256 = 1.0 |
| 8 | RATIO | input rate / 48828.125, Q16.16; writing it puts the resampler on a whole sample |
| 9, 10 | AUDIO, AUDIO_LEVEL | one stereo sample: R x 65536 + L (8192 places); write 10 to empty the FIFO |
| 11, 12 | TONE_L, TONE_R | test tones |
| 13 | AM_DEPTH | Q15 |
| 14 | LEVEL | carrier width (512 = full), [16] key for the carrier mode |
| 15 | RDS_N | blocks per bank, [16] bank asked for, [17] bank on air |
| 16, 17 | SYM_LO, SYM_HI | one symbol: offset, phase / width, time in us (17 queues it) |
| 18 | SYM_LEVEL | symbols waiting; write to empty the queue |
| 19 | CAPTURE | write 1: record 4096 MPX samples, 3: 2048 I / Q pairs (slots 3 to 6) |
| 20, 21 | RDS_LOG, RDS_LOG_LEVEL | the RDS bits sent, 32 per word |
| 22..24 | PEAK_L, PEAK_R, PEAK_MPX | largest level since the last read |
| 25 | RF_HZ | rising edges counted at the pin per second |
| 26, 27 | UNDERRUNS, SYM_UNDER | gaps in the sound / in the symbols |
| 28, 29 | STATUS, ID | [0] 250 MHz clock locked; "FMTX" |
| 30 | RF_HIGH | 250 MHz samples with the pin high in the last 0.1 s (25 000 000 = always) |

# The self-test

**Self-test** on the project card measures 41 things on your board, with nothing connected: the MPX levels (1 kHz, the pilot, the stereo side bands), the stereo signal decoded back (more than 90 dB between left and right), the 15 kHz filter, the pre-emphasis, the RDS waveform demodulated bit by bit, the RDS data decoded back to the station name, the carrier counted at the pin at 27.12 and 40.68 MHz (ISM frequencies, for a few seconds), the FM deviation as a shift of the carrier, the power setting and AM as the time the pin is high (at 6.78 MHz, ISM), USB (the other side band captured inside the FPGA, the 1 kHz tone at +1000 Hz at the pin), LSB (-1000 Hz), DSB, I/Q (+5 and -8 kHz land on their own side, the other side more than 50 dB down; flat from 2 to 12 kHz; +1 kHz at the pin), the NFM voice filter, the PSK phase path, the symbol player, the sound resampler and the FIFOs.

On the PC, `pc_app/tests` also decodes CW, RTTY and PSK31 back to text, decodes the SSTV sound back to pixels, and drives the whole service on the board (songs, RDS, pictures, an AES67 stream from the PC). `radio_modes_test.py` (42 checks, on the PC) compares the WSPR symbols with another encoder, looks at the waterfall picture with an FFT line by line (every lit pixel within 1.5 dB of its brightness, black pixels more than 25 dB down, nothing outside the picture), reads the Hell letters back, decodes the APRS frame and the DTMF keys and times WEFAX and every SSTV mode. `radio_gen_test.py` (21 checks) runs every new mode on the board on 27.12 MHz.

# Learn from it

| Idea | Where to see it |
|---|---|
| A numerically controlled oscillator | the 32-bit RF phase at 500 million samples per second |
| Frequency modulation | the MPX signal adds to the phase step |
| Stereo multiplex | L+R, a 19 kHz pilot, L-R on 38 kHz, RDS on 57 kHz |
| Digital data on a radio signal | RDS: groups, check words, biphase symbols |

## Exercises

1. FM broadcast deviates +-75 kHz. With a 32-bit phase at 500 MHz, how big is the phase step change for 75 kHz?

<details><summary>Answer</summary>
75 000 x 2^32 / 500 000 000 = 644 245 steps: the MPX value is scaled to that at full level.
</details>

2. Why is the stereo pilot exactly 19 kHz, half of the 38 kHz subcarrier?

<details><summary>Answer</summary>
The receiver doubles the pilot to rebuild the 38 kHz carrier in exact phase, and demodulates L-R with it. RDS at 57 kHz is the third harmonic, locked too.
</details>

3. RDS sends 1187.5 bits per second. How long does a station name (4 groups of 104 bits) take?

<details><summary>Answer</summary>
416 bits / 1187.5 = 0.35 s; in practice the name is sent between other groups, so receivers show it within a second or two.
</details>

# Ideas

- A **band-pass filter** (or a 110 MHz low-pass) between the pin and the antenna removes the harmonics; a small amplifier is only allowed with a licence.
- **Time signal**: the board's clock goes out in RDS every minute; send a beep every hour with the test tones.
- Use the **I2S audio** project's microphone or line input as a live source (copy both blocks into one design).

# If something is wrong

- **No station name**: RDS needs a good signal. Move closer, check that RDS is on and the RDS share is 3 to 5 %.
- **No stereo lamp**: stereo on, the pilot share 8 to 10 %, and a strong enough signal (radios switch to mono when it is weak).
- **Hiss or distortion**: lower the volume until the MPX meter stays below 0 dB; the sound share plus pilot plus RDS should stay at or below 100 %.
- **Gaps in the songs**: the status shows gaps per second; very large WAV files at 96 kHz need more of the ARM's time. Use 44.1 or 48 kHz.
- **No network streams listed / nothing received**: use **From this PC** in the app (it does not depend on the network card); for a program that announces itself, use **pass on to the radio**. A sender on another device must send to the board's network: in its settings choose the network card that leads to the board, or send unicast to the board's address. RAVENNA devices that announce only with mDNS / RTSP (not SAP): type their stream's address and port.
- **The picture is slanted or the colours are off**: choose the same SSTV mode in the decoder, or let it detect the VIS code; a weak signal blurs it.
- **Power shows "lowest clean power"**: at FM frequencies the pin cannot make weaker clean pulses; use a resistor or a shorter antenna.
- **The pin counter shows 0**: the transmitter is off, the power is 0, or the frequency is above 125 MHz (the counter cannot follow; the carrier is still there).
- **The waterfall picture is blurred, flat or tall, or upside down**: see "A picture in the waterfall" above (the receiver's FFT size, the speed, "bottom line first").
- **WSPR does not start**: it waits for the next even minute; the board's clock must be right (connect the app). The call sign must be a plain one (like K1ABC), the locator 4 characters.
