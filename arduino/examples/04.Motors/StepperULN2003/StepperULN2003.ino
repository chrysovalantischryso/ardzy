/*
  StepperULN2003: the small 28BYJ-48 stepper motor with its ULN2003 driver board.

  What it does:
    One full turn one way, a pause, one turn back, again and again. Half steps: smooth and quiet.
    2048 steps (half steps: 4096) make one turn of the motor's shaft.

  You need:
    a 28BYJ-48 motor (5 V version) with a ULN2003 board, 6 wires, and a 5 V supply for the motor
    (a USB charger or a 5 V phone power bank: the motor takes about 250 mA, more than the board's pins give).

  Wiring:
    ULN2003 IN1  <---  J1 pin 5
    ULN2003 IN2  <---  J1 pin 11
    ULN2003 IN3  <---  J1 pin 12
    ULN2003 IN4  <---  J1 pin 15
    ULN2003 GND  ----  J1 pin 9 (GND)   and the GND of the 5 V supply
    ULN2003 +5V  ----  +5 V of the 5 V supply   (NOT to any pin of Ardzy)
    The motor's white plug goes into the ULN2003 board.

    Connector pins (the same on J1..J9): I/O 5, 11, 12, 15; I2C 3 = SDA, 4 = SCL; 3.3 V out 16;
    GND 1, 2, 9, 10, 13, 14. Where each pin is: the app's Map view, or Examples, How to connect.

  Try:
    Change SPEED (half steps per second, up to about 800) and watch how fast and how strong it turns.
*/

const int IN[4] = {J1_5, J1_11, J1_12, J1_15};
const int STEPS_PER_TURN = 4096;         // half steps
const float SPEED = 700;                 // half steps per second

// half steps: one coil, two coils, one coil ... (8 patterns, then again)
const uint8_t PATTERN[8] = {0b1000, 0b1100, 0b0100, 0b0110, 0b0010, 0b0011, 0b0001, 0b1001};
int phase = 0;

void step(int dir) {
  phase = (phase + (dir > 0 ? 1 : 7)) % 8;
  for (int k = 0; k < 4; k++) digitalWrite(IN[k], (PATTERN[phase] >> (3 - k)) & 1);
}

void turn(long steps) {
  unsigned long gap = 1000000UL / SPEED, t = micros();
  for (long i = 0; i < labs(steps); i++) {
    step(steps > 0 ? 1 : -1);
    t += gap;
    long wait = (long)(t - micros());
    if (wait > 0) delayMicroseconds(wait);
  }
  for (int k = 0; k < 4; k++) digitalWrite(IN[k], LOW);   // coils off while standing: the motor stays cool
}

void setup() {
  Serial.begin(115200);
  for (int k = 0; k < 4; k++) pinMode(IN[k], OUTPUT);
  Serial.println("28BYJ-48: one turn each way");
}

void loop() {
  Serial.println("forward");
  turn(STEPS_PER_TURN);
  delay(500);
  Serial.println("back");
  turn(-STEPS_PER_TURN);
  delay(500);
}
