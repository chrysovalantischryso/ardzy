/*
  Blink without delay(): the loop keeps running and checks the time with millis().
*/
const long interval = 500;
unsigned long previous = 0;
int state = LOW;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  unsigned long now = millis();
  if (now - previous >= interval) {
    previous = now;
    state = (state == LOW) ? HIGH : LOW;
    digitalWrite(LED_BUILTIN, state);
  }
}
