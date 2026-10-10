# ardzy.sh: the Ardzy board from a bash script.   Use it with:  source ./ardzy.sh
#
#   led green on            # status LED: green, red (S9 also ps); on or off
#   beep 0.1                # buzzer, seconds (a board without one only waits)
#   if button ip; then ...  # true while pressed: ip or reset (EBAZ4205: also s2, s3)
#   v=$(peek 0x41200000)    # 32-bit FPGA register at an address (Vivado's Address Editor)
#   poke 0x41200000 5
#   v=$(reg 1 3); reg_write 1 3 42     # word 3 of slot 1 of an Ardzy FPGA project
#   watch speed 12.5        # a live value for the app's Watch tab and Plotter
#
# Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
# behind it can hang the board until it is reset. peek/poke start a small program each time
# (about 0.1 s): for fast register work use C, C++, Go or Rust.

ARDZY_BUS_BASE=$((0x43C00000))

# The board's LEDs, buttons and buzzer: name -> "GPIO level-that-means-on", from /run/ardzy/board-io.txt
# (written at boot; every Ardzy board has its own). Without it: the Antminer S9.
declare -A ARDZY_IO
if [ -r /run/ardzy/board-io.txt ]; then
  while read -r _n _g _o; do
    case "$_n" in ''|'#'*) continue ;; esac
    ARDZY_IO[$_n]="$_g $_o"
  done < /run/ardzy/board-io.txt
fi
if [ ${#ARDZY_IO[@]} -eq 0 ]; then
  ARDZY_IO=([led_green]="38 1" [led_red]="37 1" [led_ps]="15 0" [buzzer]="39 1" [button_ip]="51 0" [button_reset]="47 0")
fi

_ardzy_gpio() { echo "$2" > "/sys/class/gpio/gpio$1/value"; }

led() {
  local e=${ARDZY_IO[led_$1]:-}
  [ -n "$e" ] || { echo "led: this board has no LED \"$1\" (see /run/ardzy/board-io.txt)" >&2; return 2; }
  set -- "$1" "${2:-on}" $e                  # $3 = GPIO, $4 = the level that means on
  if [ "$2" = off ]; then _ardzy_gpio $3 $((1 - $4)); else _ardzy_gpio $3 $4; fi
}

beep() {
  local e=${ARDZY_IO[buzzer]:-}
  [ -n "$e" ] && _ardzy_gpio ${e% *} 1
  sleep "${1:-0.1}"
  [ -n "$e" ] && _ardzy_gpio ${e% *} 0
  return 0
}

button() {
  local e=${ARDZY_IO[button_${1:-ip}]:-}
  [ -n "$e" ] || { echo "button: this board has no button \"${1:-ip}\"" >&2; return 2; }
  [ "$(cat /sys/class/gpio/gpio${e% *}/value)" = "${e#* }" ]
}

peek() { local r; r=$(ardzy peek "$1") || return 1; printf '%d\n' "${r##* }"; }
poke() { ardzy poke "$1" "$2"; }
reg() { peek $((ARDZY_BUS_BASE + $1 * 0x1000 + 4 * $2)); }
reg_write() { poke $((ARDZY_BUS_BASE + $1 * 0x1000 + 4 * $2)) "$3"; }

watch() {
  if [[ "$2" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then echo "$1:$2"; else echo "$1=\"$2\""; fi
}
