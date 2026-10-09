-- __NAME__: a Lua program on the Ardzy board.
-- Press Upload: it runs on the board; everything it prints shows up in the Monitor.
-- ardzy.lua has the board: led, beep, button, peek/poke (FPGA registers), watch, sleep.
--   - the green status LED blinks
--   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
--   - press the Reset button (S1): the program ends
local ardzy = require("ardzy")

print("hello from __NAME__ (Lua): press the IP button, or Reset to end")
local presses, t = 0, 0
while true do
  ardzy.led("green", t % 10 < 5)
  if ardzy.button("ip") then
    presses = presses + 1
    print("IP button pressed (" .. presses .. ")")
    ardzy.watch("presses", presses)
    ardzy.beep(0.08)
    while ardzy.button("ip") do ardzy.sleep(0.02) end   -- wait until it is released
  end
  if ardzy.button("reset") then
    print("Reset button pressed: bye!")
    ardzy.beep(0.4)
    break
  end
  -- An FPGA register (only with an FPGA design that has it), for example:
  --   local v = ardzy.reg(1, 0)
  ardzy.sleep(0.1)
  t = t + 1
end
ardzy.led("green", false)
