/*
  ServoSweep: a hobby servo on J5 pin 5 moves from 0 to 180 degrees and back.
  Servo power: 5 V from an external supply (common GND with the board); the 3.3 V signal is fine.
*/
#include <Servo.h>

Servo servo;

void setup() {
  servo.attach(J5_5);
}

void loop() {
  for (int angle = 0; angle <= 180; angle++) { servo.write(angle); delay(15); }
  for (int angle = 180; angle >= 0; angle--) { servo.write(angle); delay(15); }
}
