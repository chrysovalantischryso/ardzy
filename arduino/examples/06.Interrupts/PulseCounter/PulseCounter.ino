/*
  PulseCounter: counts rising edges on J7 pin 5 with attachInterrupt().
  For a test, the sketch makes its own pulses on J7 pin 11: connect J7 pin 11 to J7 pin 5.
*/
volatile unsigned long count = 0;

void onPulse() {
  count++;
}

void setup() {
  Serial.begin(115200);
  pinMode(J7_5, INPUT);
  attachInterrupt(digitalPinToInterrupt(J7_5), onPulse, RISING);
  analogWriteFrequency(J7_11, 50);       // 50 pulses per second
  analogWrite(J7_11, 128);
}

void loop() {
  delay(1000);
  Serial.print("pulses: ");
  Serial.println(count);
}
