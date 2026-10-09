# ardzy.sh: the Ardzy board from a bash script.   Use it with:  source ./ardzy.sh
#
#   led green on            # status LED: green, red or ps; on or off
#   beep 0.1                # buzzer, seconds
#   if button ip; then ...  # true while pressed: ip (S2) or reset (S1)
#   v=$(peek 0x41200000)    # 32-bit FPGA register at an address (Vivado's Address Editor)
#   poke 0x41200000 5
#   v=$(reg 1 3); reg_write 1 3 42     # word 3 of slot 1 of an Ardzy FPGA project
#   watch speed 12.5        # a live value for the app's Watch tab and Plotter
#
# Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
# behind it can hang the board until it is reset. peek/poke start a small program each time
# (about 0.1 s): for fast register work use C, C++, Go or Rust.

ARDZY_BUS_BASE=$((0x43C00000))

_ardzy_gpio() { echo "$2" > "/sys/class/gpio/gpio$1/value"; }

led() {
  local v=1; [ "${2:-on}" = off ] && v=0
  case "$1" in
    green) _ardzy_gpio 38 $v ;;
    red)   _ardzy_gpio 37 $v ;;
    ps)    _ardzy_gpio 15 $((1 - v)) ;;     # the PS LED is on when the pin is low
    *) echo "led: green, red or ps" >&2; return 2 ;;
  esac
}

beep() { _ardzy_gpio 39 1; sleep "${1:-0.1}"; _ardzy_gpio 39 0; }

button() {
  local n
  case "${1:-ip}" in ip) n=51 ;; reset) n=47 ;; *) echo "button: ip or reset" >&2; return 2 ;; esac
  [ "$(cat /sys/class/gpio/gpio$n/value)" = 0 ]
}

peek() { local r; r=$(ardzy peek "$1") || return 1; printf '%d\n' "${r##* }"; }
poke() { ardzy poke "$1" "$2"; }
reg() { peek $((ARDZY_BUS_BASE + $1 * 0x1000 + 4 * $2)); }
reg_write() { poke $((ARDZY_BUS_BASE + $1 * 0x1000 + 4 * $2)) "$3"; }

watch() {
  if [[ "$2" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then echo "$1:$2"; else echo "$1=\"$2\""; fi
}
