# blink: the FPGA does all the work (the 4 LEDs count by themselves).
# This program only says hello and shows the FPGA state.
from ardzy import fpga_state

print("blink loaded. FPGA state:", fpga_state())
print("Look at the board: the 4 LEDs count in binary.")
