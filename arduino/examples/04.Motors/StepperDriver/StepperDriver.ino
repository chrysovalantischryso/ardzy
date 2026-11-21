/*
  StepperDriver: a bigger stepper motor (NEMA 17) with a STEP/DIR driver (A4988, DRV8825, TMC2208 ...).

  What it does:
    Speeds up smoothly, turns 5 times, slows down, waits, and does the same the other way. The speed-up
    (a ramp) stops the motor from losing steps when it starts. The IP button stops and starts it.

  You need:
    a STEP/DIR driver module, a stepper motor (4 wires), a motor supply (12 V for most NEMA 17, 1-2 A),
    a 100 uF capacitor across the motor supply at the driver, 5 wires.

  Wiring:
    driver STEP   <---  J1 pin 5
    driver DIR    <---  J1 pin 11
    driver EN     <---  J1 pin 15        (LOW = on; or leave it open on most modules)
    driver VDD    ----  J1 pin 16 (3.3 V out)   (the driver's logic power)
    driver GND    ----  J1 pin 9 (GND)   (logic GND)
    driver VMOT / GND  ----  the 12 V motor supply (+ and -), the capacitor right there
    driver 1A 1B 2A 2B ----  the motor's two coils
    A4988: RESET and SLEEP joined together. Set the current limit on the driver first (its datasheet).

  IMPORTANT: never plug or unplug the motor while the motor supply is on (it can destroy the driver).

  Try:
    Change MICROSTEPS to what the driver's MS pins are set to, and TOP_SPEED (steps per second).
*/

const int STEP = J1_5, DIR = J1_11, EN = J1_15;
const int MICROSTEPS = 16;                       // A4988 with MS1 MS2 MS3 high = 16
const long STEPS_PER_TURN = 200L * MICROSTEPS;    // a 1.8 degree motor: 200 full steps
const float TOP_SPEED = 3200;                    // steps per second (1 turn per second at 16 microsteps)
const float ACCEL = 4000;                        // steps per second per second
bool running = true;

void move(long steps) {
  digitalWrite(DIR, steps > 0 ? HIGH : LOW);
  delayMicroseconds(5);
  long n = labs(steps);
  float v = 200;                                 // start slow
  for (long i = 0; i < n; i++) {
    long left = n - i;
    float stopDist = v * v / (2 * ACCEL);        // steps needed to stop from this speed
    if (left <= stopDist) v -= ACCEL / v;        // slow down near the end
    else if (v < TOP_SPEED) v += ACCEL / v;      // speed up
    if (v < 100) v = 100;
    digitalWrite(STEP, HIGH);
    delayMicroseconds(3);
    digitalWrite(STEP, LOW);
    delayMicroseconds((unsigned long)(1000000.0 / v) - 3);
    if (digitalRead(BUTTON_IP) == LOW) { running = false; return; }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(STEP, OUTPUT); pinMode(DIR, OUTPUT); pinMode(EN, OUTPUT);
  digitalWrite(EN, LOW);                         // driver on
  Serial.println("Stepper: 5 turns each way. IP button: stop / start.");
}

void loop() {
  if (!running) {
    digitalWrite(EN, HIGH);                      // driver off: the motor turns freely and stays cool
    Serial.println("stopped (press IP to start again)");
    while (digitalRead(BUTTON_IP) == LOW) delay(10);
    while (digitalRead(BUTTON_IP) == HIGH) delay(10);
    while (digitalRead(BUTTON_IP) == LOW) delay(10);
    digitalWrite(EN, LOW);
    running = true;
  }
  Serial.println("5 turns forward");
  move(5 * STEPS_PER_TURN);
  if (!running) return;
  delay(700);
  Serial.println("5 turns back");
  move(-5 * STEPS_PER_TURN);
  delay(700);
}
