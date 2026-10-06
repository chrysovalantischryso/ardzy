# leds_python: the ARM (Python) controls the 4 LEDs through an AXI GPIO in the FPGA.
# AXI GPIO registers: offset 0x0 = output data, offset 0x4 = direction (0 = output)
# The board's LEDs are ACTIVE LOW (0 = on), so each pattern is inverted before writing.
import time
from ardzy import MMIO

gpio = MMIO(0x41200000)      # address set in build.tcl (Vivado Address Editor)
gpio.write(0x4, 0x0)         # all 4 pins = outputs


def show(lit):
    """lit = bit pattern of the LEDs that should be ON"""
    gpio.write(0x0, ~lit & 0xF)


print("Knight Rider on the 4 LEDs. Change this file and upload again!")
pattern = [0b0001, 0b0010, 0b0100, 0b1000, 0b0100, 0b0010]
n = 0
while True:
    lit = pattern[n % len(pattern)]
    show(lit)
    if n % 25 == 0:
        print("step", n, "LEDs lit =", format(lit, "04b"), " register =", format(gpio.read(0x0), "04b"))
    n += 1
    time.sleep(0.12)
