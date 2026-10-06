/*
  Blink: the first FPGA LED (LED_BUILTIN) on for one second, off for one second.
  Other LEDs: LED1, LED2, LED3, the status LEDs LED_GREEN / LED_RED.
*/
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
  digitalWrite(LED_BUILTIN, LOW);
  delay(1000);
}
