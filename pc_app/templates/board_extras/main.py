# __NAME__: the board's own extras, no FPGA design needed (like Arduino's first sketch).
#   - the red/green status LED blinks
#   - press the "IP" button (S2): a short beep + a message in the Monitor
#   - press the "Reset" button (S1): a long beep, and the program ends
# (Ardzy's normal "ready" state, green LED on, comes back when the program ends.)
import time
from ardzy import led, beep, button

print("__NAME__: press the IP button (beep) or the Reset button (end)")
beep(0.05)
presses = 0
try:
    t = 0
    while True:
        led('green', t % 10 < 5)          # green blinks once per second
        led('red', t % 10 >= 5)           # red in between
        if button('ip'):
            presses += 1
            print("IP button pressed (%d)" % presses)
            beep(0.08)
            while button('ip'):          # wait until it is released
                time.sleep(0.02)
        if button('reset'):
            print("Reset button pressed: bye!")
            beep(0.4)
            break
        time.sleep(0.1)
        t += 1
finally:
    led('red', False)
    led('green', True)                    # back to "Ardzy ready"
