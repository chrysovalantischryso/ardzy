# __NAME__: a Python program on the Ardzy board (no FPGA change).
# Press Upload: it runs on the board, and everything you print() shows up in the Monitor.
import time

n = 0
while True:
    print("hello from __NAME__, count", n)
    n += 1
    time.sleep(1)
