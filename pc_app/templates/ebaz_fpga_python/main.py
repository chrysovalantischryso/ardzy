# __NAME__: Python drives the EBAZ4205's LEDs and header pin DATA1-5 through the FPGA design (top.v).
# Register 0 (0x4120_0000): bit 0 = green LED, bit 1 = red LED, bit 2 = DATA1-5. Status 0 (0x4120_0080): seconds.
import time
from ardzy import MMIO, watch

regs = MMIO(0x41200000)
print("__NAME__: green, red, both, DATA1-5 ... (change main.py and upload again)")
n = 0
while True:
    regs.write(0x0, [0b001, 0b010, 0b011, 0b100][n % 4])
    watch(step=n, seconds=regs.read(0x80))
    n += 1
    time.sleep(0.5)
