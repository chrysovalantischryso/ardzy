/*
  Wire.h - I2C for the Ardzy board (Arduino Wire library API).
    Wire   I2C bus 1: SDA = pin 3, SCL = pin 4 of connectors J1..J8 (all 8 share it)
    Wire1  I2C bus 2: SDA = pin 3, SCL = pin 4 of connector J9
  Both buses have 1 kOhm pull-ups to 3.3 V on the board. Controller (master) mode, 10 to 400 kHz.
*/
#ifndef ARDZY_WIRE_H
#define ARDZY_WIRE_H

#include "Arduino.h"
#include "api/HardwareI2C.h"

#define BUFFER_LENGTH 256
#define WIRE_HAS_END 1

class TwoWire : public arduino::HardwareI2C {
public:
  TwoWire(int scl, int sda) : scl_(scl), sda_(sda) {}
  void begin() override;
  void begin(uint8_t address) override { (void)address; begin(); }   // peripheral mode is not supported
  void end() override;
  void setClock(uint32_t freq) override;
  void setWireTimeout(uint32_t timeout_us = 25000, bool reset = false) { timeout_us_ = timeout_us; (void)reset; }

  void beginTransmission(uint8_t address) override;
  void beginTransmission(int address) { beginTransmission((uint8_t)address); }
  uint8_t endTransmission(bool stopBit) override;
  uint8_t endTransmission(void) override { return endTransmission(true); }

  size_t requestFrom(uint8_t address, size_t len, bool stopBit) override;
  size_t requestFrom(uint8_t address, size_t len) override { return requestFrom(address, len, true); }

  void onReceive(void (*)(int)) override {}
  void onRequest(void (*)(void)) override {}

  size_t write(uint8_t c) override;
  size_t write(const uint8_t *data, size_t n) override;
  inline size_t write(unsigned long n) { return write((uint8_t)n); }
  inline size_t write(long n) { return write((uint8_t)n); }
  inline size_t write(unsigned int n) { return write((uint8_t)n); }
  inline size_t write(int n) { return write((uint8_t)n); }
  using arduino::Print::write;

  int available() override { return (int)(rx_len_ - rx_pos_); }
  int read() override { return rx_pos_ < rx_len_ ? rx_[rx_pos_++] : -1; }
  int peek() override { return rx_pos_ < rx_len_ ? rx_[rx_pos_] : -1; }
  void flush() override {}

private:
  int scl_, sda_;
  bool on_ = false;
  uint32_t half_ns_ = 5000;
  uint32_t timeout_us_ = 25000;
  uint8_t addr_ = 0;
  uint8_t tx_[BUFFER_LENGTH], rx_[BUFFER_LENGTH];
  size_t tx_len_ = 0, rx_len_ = 0, rx_pos_ = 0;
  bool in_tx_ = false;
  // bus primitives
  void low(int idx);
  void release(int idx);
  bool get(int idx);
  void wait();
  bool scl_high();
  bool start();
  void stop();
  bool put_byte(uint8_t b);
  uint8_t get_byte(bool ack);
};

extern TwoWire Wire;
extern TwoWire Wire1;

#endif
