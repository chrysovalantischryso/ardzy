/*
  Serial.h - Ardzy serial ports.
    Serial   the Monitor of the Ardzy app (what you print appears there; what you type there
             can be read with Serial.read()). The baud rate of begin() does not matter.
    Serial1  a real UART on the FPGA pins: TX = J1 pin 11, RX = J1 pin 12 (3.3 V).
             Other pins: Serial1.setPins(rxPin, txPin) before begin().
*/
#ifndef ARDZY_SERIAL_H
#define ARDZY_SERIAL_H

#include "api/HardwareSerial.h"

class ConsoleSerial : public arduino::HardwareSerial {
public:
  void begin(unsigned long) override {}
  void begin(unsigned long, uint16_t) override {}
  void end() override {}
  int available() override;
  int peek() override;
  int read() override;
  void flush() override;
  size_t write(uint8_t c) override;
  size_t write(const uint8_t *buf, size_t n) override;
  using arduino::Print::write;
  operator bool() override { return true; }
private:
  int fd_ = -2;
  int peek_ = -1;
  void open_in();
};

class PinSerial : public arduino::HardwareSerial {
public:
  void begin(unsigned long baud) override;
  void begin(unsigned long baud, uint16_t config) override { (void)config; begin(baud); }
  void end() override;
  int available() override;
  int peek() override;
  int read() override;
  void flush() override;
  size_t write(uint8_t c) override;
  using arduino::Print::write;
  operator bool() override { return on_; }
  void setPins(int rx, int tx) { rx_ = rx; tx_ = tx; }
private:
  int rx_ = -1, tx_ = -1;
  bool on_ = false;
  int peek_ = -1;
  unsigned long baud_ = 115200;
};

extern ConsoleSerial Serial;
extern PinSerial Serial1;

#endif
