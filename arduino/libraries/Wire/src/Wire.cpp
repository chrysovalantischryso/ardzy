/*
  Wire.cpp - I2C controller done by the ARM through the FPGA pins (open drain: a line is pulled
  low by making its pin an output with value 0, and released by making it an input; the board's
  pull-ups make it 1). Clock stretching is supported.
*/
#include "Wire.h"
#include "ardzy_hw.h"
#include <time.h>

using namespace ardzy;

TwoWire Wire(SCL, SDA);
TwoWire Wire1(SCL1, SDA1);

static inline uint64_t ns_now() {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ULL + t.tv_nsec;
}

void TwoWire::low(int idx) { fpgaOutput(idx, true); }
void TwoWire::release(int idx) { fpgaOutput(idx, false); }
bool TwoWire::get(int idx) { return fpgaRead(idx); }
void TwoWire::wait() { uint64_t end = ns_now() + half_ns_; while (ns_now() < end) {} }

bool TwoWire::scl_high() {
  release(scl_);
  uint64_t limit = ns_now() + (uint64_t)timeout_us_ * 1000;
  while (!get(scl_))                         // a device may hold the clock low (stretching)
    if (ns_now() > limit) return false;
  return true;
}

void TwoWire::begin() {
  if (!ready()) fatal("Wire needs the pin-control FPGA design");
  const int lines[2] = {scl_, sda_};
  for (int p : lines) {
    PinInfo pi = pin(p);
    fpgaFunc(pi.index, 0);
    fpgaWrite(pi.index, false);              // value 0 when it drives: open drain
    release(pi.index);
  }
  scl_ = pin(scl_).index;
  sda_ = pin(sda_).index;
  on_ = true;
  // free a bus left in the middle of a byte: up to 9 clocks, then a stop
  if (!get(sda_)) {
    for (int i = 0; i < 9 && !get(sda_); i++) { low(scl_); wait(); scl_high(); wait(); }
    stop();
  }
}

void TwoWire::end() {
  if (!on_) return;
  release(scl_);
  release(sda_);
  on_ = false;
}

void TwoWire::setClock(uint32_t freq) {
  if (freq < 10000) freq = 10000;
  if (freq > 400000) freq = 400000;
  half_ns_ = 500000000u / freq;
}

bool TwoWire::start() {
  release(sda_);
  if (!scl_high()) return false;
  wait();
  low(sda_);
  wait();
  low(scl_);
  return true;
}

void TwoWire::stop() {
  low(sda_);
  wait();
  scl_high();
  wait();
  release(sda_);
  wait();
}

bool TwoWire::put_byte(uint8_t b) {
  for (int i = 7; i >= 0; i--) {
    if ((b >> i) & 1) release(sda_); else low(sda_);
    wait();
    if (!scl_high()) return false;
    wait();
    low(scl_);
  }
  release(sda_);
  wait();
  if (!scl_high()) return false;
  bool ack = !get(sda_);
  wait();
  low(scl_);
  return ack;
}

uint8_t TwoWire::get_byte(bool ack) {
  uint8_t v = 0;
  release(sda_);
  for (int i = 0; i < 8; i++) {
    wait();
    scl_high();
    v = (v << 1) | (get(sda_) ? 1 : 0);
    wait();
    low(scl_);
  }
  if (ack) low(sda_); else release(sda_);
  wait();
  scl_high();
  wait();
  low(scl_);
  release(sda_);
  return v;
}

void TwoWire::beginTransmission(uint8_t address) {
  if (!on_) begin();
  addr_ = address;
  tx_len_ = 0;
  in_tx_ = true;
}

size_t TwoWire::write(uint8_t c) {
  if (!in_tx_ || tx_len_ >= BUFFER_LENGTH) return 0;
  tx_[tx_len_++] = c;
  return 1;
}

size_t TwoWire::write(const uint8_t *data, size_t n) {
  size_t k = 0;
  while (k < n && write(data[k])) k++;
  return k;
}

uint8_t TwoWire::endTransmission(bool stopBit) {
  in_tx_ = false;
  lock();
  uint8_t err = 0;
  if (!start()) err = 5;
  else if (!put_byte(addr_ << 1)) err = 2;
  else
    for (size_t i = 0; i < tx_len_; i++)
      if (!put_byte(tx_[i])) { err = 3; break; }
  if (stopBit || err) stop();
  else { release(sda_); wait(); }            // repeated start comes next
  unlock();
  return err;
}

size_t TwoWire::requestFrom(uint8_t address, size_t len, bool stopBit) {
  if (!on_) begin();
  if (len > BUFFER_LENGTH) len = BUFFER_LENGTH;
  rx_len_ = rx_pos_ = 0;
  lock();
  if (start() && put_byte((address << 1) | 1)) {
    for (size_t i = 0; i < len; i++) rx_[i] = get_byte(i + 1 < len);
    rx_len_ = len;
  }
  if (stopBit || !rx_len_) stop();
  unlock();
  return rx_len_;
}
