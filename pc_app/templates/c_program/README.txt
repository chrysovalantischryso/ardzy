C program template.
To use FPGA registers from C: open /dev/mem and mmap() the base address
from Vivado's Address Editor (example: 0x41200000 for an AXI GPIO).
