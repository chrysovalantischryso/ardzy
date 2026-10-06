/*
  __NAME__: an Arduino sketch for the Ardzy board (Antminer S9).

  Pins: J1_5 .. J9_15 (connector J<n>, pin 5/11/12/15, 3.3 V), LED0..LED3 (LED_BUILTIN = LED0),
  LED_GREEN, LED_RED, BUZZER, BUTTON_IP. Serial = the Monitor of the app (type there to send text).
  Libraries: Wire (I2C), SPI, Servo, EEPROM built in; more in Libraries (Arduino Library Manager).
  Examples: the Examples button.
*/

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.println("Hello from __NAME__!");
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(500);
  digitalWrite(LED_BUILTIN, LOW);
  delay(500);
}
