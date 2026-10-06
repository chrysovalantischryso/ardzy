/*
  ardzy_hw.h - low level access to the S9 hardware for the Ardzy Arduino core and libraries.
  Registers of the pin-control FPGA design (projects/ardzy_io/ardzy_ctl.v) and of the ARM GPIO.
*/
#ifndef ARDZY_HW_H
#define ARDZY_HW_H

#include <stdint.h>

namespace ardzy {

// physical addresses
const uint32_t GPIO_BASE = 0x41200000;   // AXI GPIO compatible: 0x0 DATA1, 0x4 TRI1, 0x8 DATA2, 0xC TRI2
const uint32_t CTL_BASE  = 0x43C00000;   // ardzy_ctl
const uint32_t PS_GPIO   = 0xE000A000;   // ARM (MIO) GPIO controller
const uint32_t CTL_ID_V2 = 0x41525A32;

// pin kinds
enum Kind { FPGA_IO, FPGA_IN, FAN_OUT, PS_PIN, ANALOG, NONE };

struct PinInfo {
  Kind kind;
  int index;          // FPGA pin index 0..48 / signal 49..55 / MIO number
  bool active_low;    // LEDs that light on 0
};

bool begin();                       // map the registers; false (with a message) if not possible
bool ready();                       // the pin-control design answers
PinInfo pin(int p);

volatile uint32_t *gpio();          // FPGA GPIO window
volatile uint32_t *ctl();           // ardzy_ctl window (64 KB)
volatile uint32_t *psgpio();        // ARM GPIO

// FPGA pins (index 0..48)
void fpgaFunc(int idx, int func);   // 0 GPIO, 1..8 PWM0..7, 9 UART TX
int  fpgaFuncOf(int idx);
void fpgaOutput(int idx, bool on);  // GPIO output (true) or input (false)
void fpgaWrite(int idx, bool v);
bool fpgaRead(int sig);             // any of the 56 signals
uint64_t fpgaLive();                // all 56 signals at once

// ARM pins
void psWrite(int mio, bool v);
bool psRead(int mio);

// PWM channels (8): allocate one for a pin, set frequency / duty
int  pwmFor(int idx, bool allocate);          // channel or -1
void pwmRelease(int idx);
void pwmSet(int ch, double hz, double duty);  // duty 0..1
void pwmSetPulse(int ch, double hz, double high_us);
double fclk();                                 // FCLK0 in Hz

// misc
void lock();
void unlock();
void fatal(const char *msg);

}  // namespace ardzy

#endif
