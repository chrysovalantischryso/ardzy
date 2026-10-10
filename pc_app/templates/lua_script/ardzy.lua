-- ardzy.lua: the Ardzy board from Lua.   Use it with:  local ardzy = require("ardzy")
--
--   ardzy.led("green", true)            -- status LED: "green", "red" (S9 also "ps")
--   ardzy.beep(0.1)                     -- buzzer, seconds
--   if ardzy.button("ip") then ... end  -- true while pressed: "ip" or "reset" (EBAZ4205: also "s2", "s3")
--   local v = ardzy.peek(0x41200000)    -- 32-bit FPGA register at an address (Vivado's Address Editor)
--   ardzy.poke(0x41200000, 5)
--   ardzy.reg(1, 3); ardzy.reg_write(1, 3, 42)   -- word 3 of slot 1 of an Ardzy FPGA project
--   ardzy.watch("speed", 12.5)          -- a live value for the app's Watch tab and Plotter
--   ardzy.sleep(0.5)                    -- wait, seconds (like Arduino's delay)
--
-- Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
-- behind it can hang the board until it is reset.
local M = { BUS_BASE = 0x43C00000 }
-- The board's LEDs, buttons and buzzer: name -> { GPIO, the level that means on / pressed }, from
-- /run/ardzy/board-io.txt (written at boot; every Ardzy board has its own). Without it: the Antminer S9.
local IO = {}
do
  local f = io.open("/run/ardzy/board-io.txt", "r")
  if f then
    for line in f:lines() do
      local n, g, on = line:match("^%s*([%w_]+)%s+(%d+)%s+(%d)")
      if n then IO[n] = { tonumber(g), tonumber(on) } end
    end
    f:close()
  end
  if next(IO) == nil then
    IO = { led_green = { 38, 1 }, led_red = { 37, 1 }, led_ps = { 15, 0 }, buzzer = { 39, 1 },
           button_ip = { 51, 0 }, button_reset = { 47, 0 } }
  end
end

io.stdout:setvbuf("line")     -- print each line at once (the Monitor shows it immediately)

local function gpio_set(n, v)
  local f = assert(io.open("/sys/class/gpio/gpio" .. n .. "/value", "w"))
  f:write(v and "1" or "0")
  f:close()
end

local function gpio_get(n)
  local f = assert(io.open("/sys/class/gpio/gpio" .. n .. "/value", "r"))
  local v = f:read(1)
  f:close()
  return v == "1"
end

-- FPGA registers and sleep: through the board's register helper (Lua cannot map memory or sleep by
-- itself). It runs beside the program: commands go into its input, answers come back through a named pipe.
local rd, wr
local function regd(cmd)
  if not wr then
    local h = os.getenv("ARDZY_REGD") or error("the register helper is missing (start the program with Upload)")
    local fifo = os.tmpname()
    os.remove(fifo)
    assert(os.execute("mkfifo '" .. fifo .. "'"), "mkfifo failed")
    wr = assert(io.popen("exec '" .. h .. "' > '" .. fifo .. "'", "w"))
    rd = assert(io.open(fifo, "r"))
    os.remove(fifo)
  end
  wr:write(cmd, "\n")
  wr:flush()
  local ans = rd:read("l") or error("register helper stopped")
  if ans:sub(1, 5) == "error" then error(ans, 3) end
  return ans
end

function M.sleep(seconds)
  regd(string.format("s %d", math.floor(math.max(0, seconds) * 1e6)))
end

function M.led(name, on)
  local l = IO["led_" .. name] or error('led: this board has no LED "' .. name .. '" (see /run/ardzy/board-io.txt)', 2)
  if on == nil then on = true end
  gpio_set(l[1], (on and true or false) == (l[2] == 1))
end

function M.beep(seconds)                     -- (a board without a buzzer only waits)
  local b = IO.buzzer
  if b then gpio_set(b[1], true) end
  M.sleep(seconds or 0.1)
  if b then gpio_set(b[1], false) end
end

function M.button(name)
  name = name or "ip"
  local b = IO["button_" .. name] or error('button: this board has no button "' .. name .. '"', 2)
  return gpio_get(b[1]) == (b[2] == 1)
end

function M.peek(addr) return math.tointeger(tonumber(regd(string.format("r %d", addr & 0xFFFFFFFF)))) end
function M.poke(addr, value) regd(string.format("w %d %d", addr & 0xFFFFFFFF, value & 0xFFFFFFFF)) end
function M.reg(slot, word) return M.peek(M.BUS_BASE + slot * 0x1000 + 4 * word) end
function M.reg_write(slot, word, value) M.poke(M.BUS_BASE + slot * 0x1000 + 4 * word, value) end

function M.watch(name, value)
  if type(value) == "number" then print(name .. ":" .. value)
  elseif type(value) == "boolean" then print(name .. ":" .. (value and 1 or 0))
  else print(name .. '="' .. tostring(value):gsub('"', "'") .. '"') end
end

return M
