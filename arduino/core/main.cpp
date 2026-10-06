/*
  main.cpp - runs setup() once, then loop() forever, like every Arduino.
  When the app stops the program (or you press Ctrl+C), every FPGA pin goes back to input.
*/
#include "Arduino.h"
#include "ardzy_hw.h"
#include <signal.h>
#include <stdio.h>
#include <unistd.h>

void serialEvent() __attribute__((weak));
void serialEvent1() __attribute__((weak));
void initVariant() __attribute__((weak));
void initVariant() {}

static void safe_stop(int) {
  if (ardzy::ready()) {
    volatile uint32_t *c = ardzy::ctl(), *g = ardzy::gpio();
    for (int i = 0; i < 7; i++) c[(0x40 >> 2) + i] = 0;    // pins back to GPIO
    g[1] = 0xFFFFFFFF; g[3] = 0x1FFFF;                    // ... and inputs
    c[0xE0 >> 2] &= ~(1u << 31);                         // UART off
  }
  _exit(0);
}

void init(void) {
  setvbuf(stdout, nullptr, _IOLBF, 0);                   // printf() lines show at once
  if (!ardzy::begin())
    fprintf(stderr, "ardzy: the pin-control FPGA design is not loaded: pins are not available "
                    "(time, Serial and board functions still work)\n");
  signal(SIGTERM, safe_stop);
  signal(SIGINT, safe_stop);
  signal(SIGPIPE, SIG_IGN);
}

int main() {
  init();
  initVariant();
  setup();
  for (;;) {
    loop();
    if (serialEvent && Serial.available()) serialEvent();
    if (serialEvent1 && Serial1.available()) serialEvent1();
  }
  return 0;
}
