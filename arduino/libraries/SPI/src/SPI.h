/*
  SPI.h - SPI controller for the Ardzy board (Arduino SPI library API).
  Default pins on connector J2: SS = pin 5 (J2_5), MOSI = pin 11, MISO = pin 12, SCK = pin 15.
  Other pins: SPI.setPins(sck, miso, mosi) before begin(). Modes 0..3, MSB or LSB first.
  The clock is made by the ARM (up to about 1 MHz); SPISettings asks for a maximum speed.
  Chip select is yours to drive: pinMode(SS, OUTPUT); digitalWrite(SS, LOW) ... HIGH.
*/
#ifndef ARDZY_SPI_H
#define ARDZY_SPI_H

#include "Arduino.h"
#include "api/HardwareSPI.h"

#define SPI_HAS_TRANSACTION 1

class ArdzySPI : public arduino::HardwareSPI {
public:
  uint8_t transfer(uint8_t data) override;
  uint16_t transfer16(uint16_t data) override;
  void transfer(void *buf, size_t count) override;
  void usingInterrupt(int) override {}
  void notUsingInterrupt(int) override {}
  void beginTransaction(arduino::SPISettings settings) override;
  void endTransaction(void) override {}
  void attachInterrupt() override {}
  void detachInterrupt() override {}
  void begin() override;
  void end() override;
  void setPins(int sck, int miso, int mosi) { sck_ = sck; miso_ = miso; mosi_ = mosi; }
  // older API
  void setBitOrder(BitOrder order) { order_ = order; }
  void setDataMode(uint8_t mode) { mode_ = mode & 3; idle(); }
  void setClockDivider(uint8_t div) { half_ns_ = div * 31; }
private:
  int sck_ = SCK, miso_ = MISO, mosi_ = MOSI;
  uint8_t mode_ = 0;
  BitOrder order_ = MSBFIRST;
  uint32_t half_ns_ = 500;
  bool on_ = false;
  void idle();
  void wait();
};

extern ArdzySPI SPI;

#define SPI_CLOCK_DIV2 2
#define SPI_CLOCK_DIV4 4
#define SPI_CLOCK_DIV8 8
#define SPI_CLOCK_DIV16 16
#define SPI_CLOCK_DIV32 32
#define SPI_CLOCK_DIV64 64
#define SPI_CLOCK_DIV128 128

#endif
