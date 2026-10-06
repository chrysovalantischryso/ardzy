/*
  Button: the board's IP button switches the green status LED.
  The buttons read LOW while pressed. A push button on a connector pin works the same way
  (pins have a weak pull-up: wire the button between the pin and GND).
*/
void setup() {
  pinMode(LED_GREEN, OUTPUT);
  pinMode(BUTTON_IP, INPUT);
}

void loop() {
  if (digitalRead(BUTTON_IP) == LOW) {
    digitalWrite(LED_GREEN, HIGH);
  } else {
    digitalWrite(LED_GREEN, LOW);
  }
}
