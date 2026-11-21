# Ardzy roadmap

What is planned next, and how. The newest work is listed in the README under "In development".

## Next: step debugging for sketches (like the Arduino IDE 2 debugger)

Goal: breakpoints, step over / into / out, the call stack, local and global variables (and changing them),
all in the Code view, for Arduino sketches and C / C++ programs on the board.

How (decided, not built yet):

- **gdb runs on the board**, driven through its machine interface (GDB/MI, `gdb --interpreter=mi3`), a line-based
  text protocol made for front ends. The board has no gdb yet: it installs from the app like a language
  (Settings, Languages: the PC downloads the Debian `gdb` package for armhf, the board installs it). No ARM gdb
  is needed on the PC, and no gdbserver.
- **Board side**: `opt/ardzy/web/debug.py`, one gdb session at a time, started by `POST /api/debug/start?p=<project>`.
  It builds the sketch with `-Og -g` (build.py gets a debug flag; the normal build stays `-O2`), stops the
  running program, starts gdb on the new one, and answers `/api/debug/{break,run,next,step,finish,stop,vars,stack,eval}`.
  Every answer is the parsed MI record (JSON). Program output keeps going to the Monitor.
- **App side**: `ui/debug.js`: breakpoints in the editor gutter (click), a Debug toolbar (Continue F5, Step over F10,
  Step into F11, Step out Shift+F11, Stop), the current line marked, and a bottom tab with the call stack and the
  variables (expand structs and arrays; change a value). The `#line` marks build.py writes into `sketch.ino.cpp`
  already map back to the `.ino` lines.
- **Safety**: a program stopped at a breakpoint keeps its FPGA design and pins as they were; Stop always ends
  gdb and the program. A watchdog ends a gdb session nobody talks to for 10 minutes.
- **Test plan**: the MI parser with recorded gdb output (no board needed), then on the real board: a breakpoint
  in `loop()`, step through `digitalWrite`, read a global, change it, continue; the same for a C++ project.

References: the GDB manual's GDB/MI chapter (sourceware.org/gdb), the list of GDB front ends on the GDB wiki,
and the Arduino IDE 2 debugger tutorial (docs.arduino.cc), which shows the expected features.

## From issue 1 (feature request)

- Done (in development): the app over a USB-UART cable, and a terminal in the app.
- **Android app**: the same link (ardzy_link.py frames) over a USB-UART adapter on a phone (USB OTG). The phone app
  would carry the link's PC end; the board end is already done.
- **A light desktop (LXDE or similar)**: the board has no display output, so it would be shown in the app (VNC);
  512 MB and 667 MHz make it slow. As an optional install (like the languages), not in the default image.
- **USB, HDMI, audio from the FPGA**: video and audio already exist as ready projects (07_vga, 08_audio). HDMI needs
  differential pairs on the header pins and the serializer (OSERDES), which does not work yet with the built-in
  toolchain (Vivado can); a USB 1.1 host in the FPGA is possible but a large job.
- Power: the board runs from 5 V; not from 3.3 V or 3 V (its regulators need more than 3.3 V in to make 3.3 V).

## Also planned

- Learn challenges checked automatically with the logic analyzer (needs the board for testing).
- Python package manager for the board (the PC downloads wheels or Debian packages, like the languages).
- SD card backup and restore in the app (read a card into an `.img`, write it back).
- Network setup: Wi-Fi dongle or USB network, from the app.
- NeoPixel (WS2812) block: needs an FPGA block for the exact timing (Linux on the ARM cannot keep 0.4 us pulses).

## Not planned, and why

- **Fan profiles in the background**: the fan PWM lives inside the FPGA design (the pin-control design). A service
  that writes it while another design is loaded would read or write an empty FPGA address, which can stop the
  board. Fans stay under the program's control (Blocks: "set the fans to", Arduino: `Ardzy.fan()`).
- **A separate autostart manager**: "at boot" (the project that starts with the board) already does this.
