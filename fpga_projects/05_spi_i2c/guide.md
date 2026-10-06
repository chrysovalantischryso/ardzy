# What it does

Hardware SPI and I2C controllers for sensors, displays, memories and clocks: exact bus timing from the FPGA, buffers so the ARM writes a whole message at once, and up to 50 MHz SPI. The demo scans the I2C bus, names what it finds (BME280 / BMP280, DS3231 clock, SSD1306 display ...) and reads the ID of an SPI flash chip.

# How it works

## SPI

SPI has 4 wires: **SCLK** (clock from the master), **MOSI** (master out), **MISO** (master in) and **CS** (chip select, low = talking). Every clock both sides shift one bit: sending and receiving happen together. The 4 SPI **modes** say on which clock edge the data changes (CPOL = clock level when idle, CPHA = which edge reads).

The FPGA block has a 64-word send buffer and a 64-word receive buffer, words of 1 to 32 bits, MSB or LSB first, all 4 modes, and SCLK = 100 MHz / (2 x (DIV + 1)): 50 MHz, 25 MHz ... down to slow. With automatic chip select, CS stays low while the words go back to back.

## I2C

I2C has 2 wires shared by many devices, each with a 7-bit address: **SDA** (data) and **SCL** (clock). Both are **open drain**: devices only pull the lines low; resistors pull them high (the board has 1 kohm pull-ups on its I2C pins). A message: START, the address and a read / write bit, bytes each answered with an ACK, STOP.

The ARM queues **commands** (START, WRITE byte, READ with ACK, READ with NACK, STOP); the FPGA runs them with exact timing (100 kHz, 400 kHz, 1 MHz) and queues the results. It also waits when a slow device holds SCL low (clock stretching), with a timeout.

# Try it

| Device | Wiring |
|---|---|
| SPI flash (W25Q32, W25Q64) | CS to J2 pin 5, DI to J2 pin 11, DO to J2 pin 12, CLK to J2 pin 15, VCC 3.3 V, GND |
| I2C sensor / display | SDA to pin 3, SCL to pin 4 of any of J1..J8, VCC 3.3 V, GND |

**Upload and run**: the Monitor lists the I2C devices found and the flash chip's ID (for example EF 40 17 = Winbond W25Q64).

# Program it

```python
from blocks import Bus, SPI, I2C
spi = SPI(Bus(), slot=1)
spi.setup(hz=10_000_000, mode=0, bits=8)
print(spi.transfer([0x9F, 0, 0, 0]))          # JEDEC ID: [x, maker, type, size]

i2c = I2C(Bus(), slot=2, hz=400_000)
print([hex(a) for a in i2c.scan()])           # e.g. ['0x3c', '0x68', '0x76']
i2c.write(0x76, bytes([0xF4, 0x27]))          # BME280: start measuring
print(i2c.read(0x76, 6, reg=0xF7))            # 6 bytes from register 0xF7
```

## SPI registers (slot 1)

| Word | Name | Meaning |
|---|---|---|
| 0 | CTRL | [0] CPHA [1] CPOL [2] LSB first [3] loopback [4] automatic CS |
| 1 | DIV | SCLK = 100 MHz / (2 x (DIV + 1)) |
| 2 | WIDTH | bits per word, 1..32 |
| 3, 4 | TX, RX | send a word / take a received word |
| 5 | STATUS | words waiting, received words, busy, overflow |
| 6 | CS | chip select level (manual mode) |
| 7 | ID | "SPIM" |

## I2C registers (slot 2)

| Word | Name | Meaning |
|---|---|---|
| 0 | CMD | queue: [10:8] 1 START, 2 STOP, 3 WRITE, 4 READ+ACK, 5 READ+NACK; [7:0] data |
| 1 | RESULT | [31] valid, [9] from a READ, [8] ACK, [7:0] byte |
| 2 | STATUS | commands / results waiting, busy, SCL and SDA levels, timeout |
| 3, 4 | DIV, TIMEOUT | speed, clock stretching limit |
| 5 | ID | "I2CM" |

# Learn from it

| Idea | Where to see it |
|---|---|
| Shift registers: send and receive at the same time | SPI: every SCLK edge shifts a bit out and a bit in |
| Clock polarity and phase (modes 0..3) | CPOL, CPHA in the control register |
| Open-drain buses shared by many devices | I2C: devices only pull low, resistors pull high |
| A command queue between software and exact timing | the ARM queues START, WRITE, READ, STOP; the FPGA runs them |

## Exercises

1. SPI at DIV = 4: what clock frequency, and how long for a 16-bit word?

<details><summary>Answer</summary>
100 MHz / (2 x 5) = 10 MHz; 16 bits take 1.6 us.
</details>

2. Why must I2C lines be open drain with pull-up resistors?

<details><summary>Answer</summary>
Several devices share one wire. If any could drive it high while another drives it low, they would short. With open drain they can only pull low; the resistor makes high. Clock stretching and acknowledges work because anyone may hold a line low.
</details>

3. An I2C device does not answer its address. What does the master see?

<details><summary>Answer</summary>
No ACK: SDA stays high (the pull-up) in the ninth clock. The FPGA reports a NACK; usually a wrong address, a missing pull-up or a device without power.
</details>

# Ideas

- An SSD1306 OLED showing the board's temperature; a BME280 weather station with the plotter.
- Read and write a whole SPI flash (save data, or reprogram another board's flash).
- An SPI display (ST7789) at 50 MHz: fast enough for animation.

# If something is wrong

- **I2C scan finds nothing**: check SDA / SCL are not swapped and the device has power. Very long wires: lower the speed.
- **SPI reads 0xFF**: MISO not connected (the pull-up reads high) or wrong mode; most chips use mode 0.
- **Garbage at high SPI speed**: long wires; keep them short or go down to 10 MHz.
