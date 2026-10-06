/*
  Arduino.h - Ardzy core: the Arduino API on the Antminer S9 board (Zynq XC7Z010, Linux).

  Your sketch runs as a normal Linux program on the ARM. The pins are FPGA pins, driven through
  the Ardzy pin-control design (loaded automatically for sketches). Everything Arduino code
  expects is here: pinMode / digitalWrite / digitalRead / analogWrite / analogRead, millis,
  delay, Serial (the app's Monitor), Serial1 (a UART on any pins), tone, pulseIn, shiftOut,
  attachInterrupt, plus the libraries Wire, SPI, EEPROM and Servo.

  The hardware-independent part (String, Print, Stream, ...) is the official ArduinoCore-API
  (LGPL 2.1, https://github.com/arduino/ArduinoCore-API) in the api/ folder.
*/
#ifndef ARDZY_ARDUINO_H
#define ARDZY_ARDUINO_H

#include "api/ArduinoAPI.h"

#if defined(__cplusplus)
using namespace arduino;
#endif

#include "pins_ardzy.h"

#ifdef __cplusplus
extern "C" {
#endif

// ---- extras of this board (C callable)
void analogReadResolution(int bits);       // default 10 (like an Uno)
void analogWriteResolution(int bits);      // default 8 (0..255)
void analogWriteFrequency(pin_size_t pin, float hz);   // PWM frequency of one pin (default 1000 Hz)
void interrupts(void);
void noInterrupts(void);

#ifdef __cplusplus
}
#endif

#ifdef __cplusplus
#include "Serial.h"

// The board itself: status LEDs, buzzer, fans, temperature, FPGA clock.
class ArdzyBoard {
public:
  void beep(unsigned int ms = 100);            // the on-board buzzer
  float temperature();                         // chip temperature in degrees C
  float voltage(const char *rail);             // "vccint", "vccaux", "vccbram", "vccpint", "vccpaux", "vccoddr"
  void fan(int percent);                       // all 6 fan headers, 0..100 (-1 = full speed, no PWM)
  int fanRpm(int fan);                         // fan 1..6
  unsigned long fpgaClock();                   // FCLK0 in Hz
  const char *chipId();                        // the unique 57-bit Device DNA (hex)
  bool pinControlLoaded();                     // true when the pin-control FPGA design is running
  // watch: shows a value live in the app (Watch tab, Plotter) and in the board's data logger.
  // Ardzy.watch("speed", 12.5);  prints the line  speed:12.5   (text:  Ardzy.watch("state", "run")  ->  state="run")
  void watch(const char *name, double value);
  void watch(const char *name, long value);
  void watch(const char *name, int value) { watch(name, (long)value); }
  void watch(const char *name, unsigned long value) { watch(name, (long)value); }
  void watch(const char *name, unsigned int value) { watch(name, (long)value); }
  void watch(const char *name, float value) { watch(name, (double)value); }
  void watch(const char *name, bool value) { watch(name, (long)value); }
  void watch(const char *name, const char *text);
  void watch(const char *name, const String &text) { watch(name, text.c_str()); }
};
extern ArdzyBoard Ardzy;
#endif

#endif
