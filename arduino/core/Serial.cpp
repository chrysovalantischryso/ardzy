/*
  Serial.cpp - the Monitor console (Serial) and the FPGA UART (Serial1).
*/
#include "Arduino.h"
#include "ardzy_hw.h"
#include <errno.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>

using namespace ardzy;

ConsoleSerial Serial;
PinSerial Serial1;

// ------------------------------------------------------------------ Serial (the app's Monitor)
// Output goes to stdout (the Monitor). Input comes from /run/ardzy/serial_in, a pipe the board
// service writes when you type in the Monitor (or from stdin when you run the sketch yourself).
void ConsoleSerial::open_in() {
  if (fd_ != -2) return;
  fd_ = ::open("/run/ardzy/serial_in", O_RDWR | O_NONBLOCK);
  if (fd_ < 0) {
    fd_ = isatty(0) ? 0 : -1;
    if (fd_ == 0) fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK);
  }
}

int ConsoleSerial::available() {
  open_in();
  if (fd_ < 0) return peek_ >= 0;
  int n = 0;
  if (ioctl(fd_, FIONREAD, &n) < 0) n = 0;
  return n + (peek_ >= 0);
}

int ConsoleSerial::read() {
  if (peek_ >= 0) { int c = peek_; peek_ = -1; return c; }
  open_in();
  if (fd_ < 0) return -1;
  unsigned char c;
  return ::read(fd_, &c, 1) == 1 ? c : -1;
}

int ConsoleSerial::peek() {
  if (peek_ < 0) peek_ = read();
  return peek_;
}

void ConsoleSerial::flush() { fsync(1); }

size_t ConsoleSerial::write(uint8_t c) { return write(&c, 1); }

size_t ConsoleSerial::write(const uint8_t *buf, size_t n) {
  size_t done = 0;
  while (done < n) {
    ssize_t r = ::write(1, buf + done, n - done);
    if (r < 0) { if (errno == EINTR) continue; break; }
    done += r;
  }
  return done;
}

// ------------------------------------------------------------------ Serial1 (FPGA UART)
void PinSerial::begin(unsigned long baud) {
  if (!ready()) fatal("Serial1 needs the pin-control FPGA design");
  if (rx_ < 0) rx_ = PIN_SERIAL1_RX;
  if (tx_ < 0) tx_ = PIN_SERIAL1_TX;
  PinInfo tx = pin(tx_), rx = pin(rx_);
  if (tx.kind != FPGA_IO || (rx.kind != FPGA_IO && rx.kind != FPGA_IN)) fatal("Serial1: pick connector pins for RX and TX");
  baud_ = baud ? baud : 115200;
  uint32_t div = (uint32_t)(fclk() / baud_ + 0.5);
  if (div < 4 || div > 0xFFFF) fatal("Serial1: baud rate not possible at this FPGA clock");
  if (rx.kind == FPGA_IO && rx.index != tx.index) { fpgaFunc(rx.index, 0); fpgaOutput(rx.index, false); }
  pwmRelease(tx.index);
  fpgaFunc(tx.index, 9);                         // pin function 9 = UART TX (also when RX is the same pin)
  ctl()[0xE0 >> 2] = (1u << 31) | ((uint32_t)rx.index << 16) | div;
  ctl()[0xEC >> 2] = 1;                           // clear old error flags
  while (ctl()[0xEC >> 2] & 0x7FF) (void)ctl()[0xE8 >> 2];   // and old bytes
  on_ = true;
}

void PinSerial::end() {
  if (!on_) return;
  flush();
  ctl()[0xE0 >> 2] &= ~(1u << 31);
  PinInfo tx = pin(tx_);
  fpgaFunc(tx.index, 0);
  on_ = false;
}

int PinSerial::available() {
  if (!on_) return 0;
  return (int)(ctl()[0xEC >> 2] & 0x7FF) + (peek_ >= 0);
}

int PinSerial::read() {
  if (peek_ >= 0) { int c = peek_; peek_ = -1; return c; }
  if (!on_) return -1;
  uint32_t v = ctl()[0xE8 >> 2];
  return (v & 0x100) ? (int)(v & 0xFF) : -1;
}

int PinSerial::peek() {
  if (peek_ < 0) peek_ = read();
  return peek_;
}

size_t PinSerial::write(uint8_t c) {
  if (!on_) return 0;
  unsigned long t0 = millis();
  while (!(ctl()[0xE4 >> 2] & 0x7F)) {           // the 64-byte send queue is full: wait
    if (millis() - t0 > 2000) return 0;
    delayMicroseconds(20);
  }
  ctl()[0xE4 >> 2] = c;
  return 1;
}

void PinSerial::flush() {
  if (!on_) return;
  unsigned long t0 = millis();
  while ((ctl()[0xE4 >> 2] & 0x7F) < 64 && millis() - t0 < 2000) delayMicroseconds(50);
  delayMicroseconds((unsigned)(11e6 / baud_) + 1);      // the last byte on the wire
}
