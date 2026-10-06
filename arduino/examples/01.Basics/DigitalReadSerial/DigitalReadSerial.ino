/*
  DigitalReadSerial: reads connector J3 pin 5 and prints it in the Monitor.
*/
void setup() {
  Serial.begin(115200);
  pinMode(J3_5, INPUT_PULLUP);
}

void loop() {
  int state = digitalRead(J3_5);
  Serial.println(state);
  delay(200);
}
