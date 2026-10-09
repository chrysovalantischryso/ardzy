#!/bin/bash
# __NAME__: a bash script on the Ardzy board.
# Press Upload: it runs on the board; everything it prints (echo) shows up in the Monitor.
# ardzy.sh has the board: led, beep, button, peek/poke (FPGA registers), watch.
#   - the green status LED blinks
#   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
#   - press the Reset button (S1): the script ends
source ./ardzy.sh

echo "hello from __NAME__ (bash): press the IP button, or Reset to end"
presses=0
t=0
while true; do
  if [ $((t % 10)) -lt 5 ]; then led green on; else led green off; fi
  if button ip; then
    presses=$((presses + 1))
    echo "IP button pressed ($presses)"
    watch presses $presses
    beep 0.08
    while button ip; do sleep 0.02; done     # wait until it is released
  fi
  if button reset; then
    echo "Reset button pressed: bye!"
    beep 0.4
    break
  fi
  sleep 0.1
  t=$((t + 1))
done
led green off
