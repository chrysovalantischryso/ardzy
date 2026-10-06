/*
  SPI.cpp - SPI controller made by the ARM on FPGA pins.
*/
#include "SPI.h"
#include "ardzy_hw.h"
#include <time.h>

using namespace ardzy;

ArdzySPI SPI;

static inline uint64_t ns_now() {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ULL + t.tv_nsec;
}

void ArdzySPI::wait() {
  if (half_ns_ < 300) return;                 // the register writes alone take about that long
  uint64_t end = ns_now() + half_ns_;
  while (ns_now() < end) {}
}

void ArdzySPI::idle() {
  if (on_) fpgaWrite(pin(sck_).index, mode_ >= 2);    // CPOL
}

void ArdzySPI::begin() {
  if (!ready()) fatal("SPI needs the pin-control FPGA design");
  pinMode(sck_, OUTPUT);
  pinMode(mosi_, OUTPUT);
  pinMode(miso_, INPUT);
  on_ = true;
  idle();
}

void ArdzySPI::end() {
  if (!on_) return;
  pinMode(sck_, INPUT);
  pinMode(mosi_, INPUT);
  on_ = false;
}

void ArdzySPI::beginTransaction(arduino::SPISettings s) {
  if (!on_) begin();
  mode_ = (uint8_t)s.getDataMode();
  order_ = s.getBitOrder();
  uint32_t f = s.getClockFreq();
  half_ns_ = f ? 500000000u / f : 500;
  idle();
}

uint8_t ArdzySPI::transfer(uint8_t data) {
  if (!on_) begin();
  int sck = pin(sck_).index, mosi = pin(mosi_).index, miso = pin(miso_).index;
  bool cpol = mode_ >= 2, cpha = mode_ & 1;
  uint8_t in = 0;
  lock();
  for (int i = 0; i < 8; i++) {
    int bit = order_ == MSBFIRST ? 7 - i : i;
    bool out = (data >> bit) & 1;
    if (!cpha) {                       // data valid before the first edge
      fpgaWrite(mosi, out);
      wait();
      fpgaWrite(sck, !cpol);
      if (fpgaRead(miso)) in |= 1 << bit;
      wait();
      fpgaWrite(sck, cpol);
    } else {                           // data changes on the first edge
      fpgaWrite(sck, !cpol);
      fpgaWrite(mosi, out);
      wait();
      fpgaWrite(sck, cpol);
      if (fpgaRead(miso)) in |= 1 << bit;
      wait();
    }
  }
  unlock();
  return in;
}

uint16_t ArdzySPI::transfer16(uint16_t data) {
  uint8_t a, b;
  if (order_ == MSBFIRST) { a = transfer(data >> 8); b = transfer(data & 0xFF); return (a << 8) | b; }
  a = transfer(data & 0xFF); b = transfer(data >> 8);
  return (b << 8) | a;
}

void ArdzySPI::transfer(void *buf, size_t count) {
  uint8_t *p = (uint8_t *)buf;
  for (size_t i = 0; i < count; i++) p[i] = transfer(p[i]);
}
