/*
  Servo.cpp - 50 Hz pulses from an FPGA PWM channel.
*/
#include "Servo.h"
#include "ardzy_hw.h"

using namespace ardzy;

uint8_t Servo::attach(int p, int mn, int mx) {
  PinInfo pi = pin(p);
  if (pi.kind != FPGA_IO) return INVALID_SERVO;
  if (pin_ >= 0) detach();
  pin_ = p;
  min_ = mn;
  max_ = mx;
  int ch = pwmFor(pi.index, true);
  pwmSetPulse(ch, 1e6 / REFRESH_INTERVAL, us_);
  fpgaFunc(pi.index, 1 + ch);
  return (uint8_t)ch;
}

void Servo::detach() {
  if (pin_ < 0) return;
  PinInfo pi = pin(pin_);
  pwmRelease(pi.index);
  fpgaFunc(pi.index, 0);
  pin_ = -1;
}

void Servo::write(int value) {
  if (value < 200) {
    if (value < 0) value = 0;
    if (value > 180) value = 180;
    value = map(value, 0, 180, min_, max_);
  }
  writeMicroseconds(value);
}

void Servo::writeMicroseconds(int us) {
  if (us < min_) us = min_;
  if (us > max_) us = max_;
  us_ = us;
  if (pin_ < 0) return;
  int ch = pwmFor(pin(pin_).index, false);
  if (ch >= 0) pwmSetPulse(ch, 1e6 / REFRESH_INTERVAL, us_);
}

int Servo::read() { return map(us_, min_, max_, 0, 180); }
int Servo::readMicroseconds() { return us_; }
