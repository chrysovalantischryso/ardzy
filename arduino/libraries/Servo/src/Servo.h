/*
  Servo.h - hobby servos on any connector pin (Arduino Servo library API).
  The pulses come from the FPGA's PWM channels (exact timing, no jitter): up to 8 at a time,
  shared with analogWrite() and tone(). Servos usually need 5 V power but take the 3.3 V signal.
*/
#ifndef ARDZY_SERVO_H
#define ARDZY_SERVO_H

#include "Arduino.h"

#define MIN_PULSE_WIDTH 544
#define MAX_PULSE_WIDTH 2400
#define DEFAULT_PULSE_WIDTH 1500
#define REFRESH_INTERVAL 20000
#define MAX_SERVOS 8
#define INVALID_SERVO 255

class Servo {
public:
  uint8_t attach(int pin, int min = MIN_PULSE_WIDTH, int max = MAX_PULSE_WIDTH);
  void detach();
  void write(int value);                 // angle 0..180, or a pulse width in microseconds (>= 200)
  void writeMicroseconds(int us);
  int read();
  int readMicroseconds();
  bool attached() { return pin_ >= 0; }
private:
  int pin_ = -1, min_ = MIN_PULSE_WIDTH, max_ = MAX_PULSE_WIDTH, us_ = DEFAULT_PULSE_WIDTH;
};

#endif
