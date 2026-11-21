/*
  ExternalLedButton: your own LED and push button on a connector (the first thing to wire).

  What it does:
    The LED blinks; while you hold the button it stays on. Each press is counted in the Monitor.

  You need:
    1 LED, 1 resistor of 330 Ohm (220 .. 1k is fine), 1 push button, 4 wires (a breadboard helps).

  Wiring:
    J2 pin 5 ---[ 330 Ohm ]---|>|--- J2 pin 9 (GND)       the LED's long leg (+, anode) to the resistor,
                              LED                          the short leg (-, flat side) to GND
    J2 pin 11 ----[ button ]---- J2 pin 10 (GND)          pressed = the pin is pulled to GND (LOW)

    Connector pins (the same on J1..J9): I/O 5, 11, 12, 15; I2C 3 = SDA, 4 = SCL; 3.3 V out 16;
    GND 1, 2, 9, 10, 13, 14. Where each pin is: the app's Map view, or Examples, How to connect.

  Why the resistor: an LED alone would take too much current from the pin and could damage it.
  Why no resistor at the button: the connector pins have a pull-up inside, so an open button reads HIGH.
  The pins are 3.3 V: never connect 5 V to them.

  Try:
    Use another pin: J2_12 or J3_5 (any connector, pins 5, 11, 12, 15).
*/

const int LED_PIN = J2_5;
const int BUTTON_PIN = J2_11;
int presses = 0;
bool wasDown = false;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.println("LED on J2 pin 5, button on J2 pin 11");
}

void loop() {
  bool down = digitalRead(BUTTON_PIN) == LOW;
  if (down && !wasDown) {
    presses++;
    Serial.print("button pressed, ");
    Serial.print(presses);
    Serial.println(" times so far");
    Ardzy.watch("presses", presses);
  }
  wasDown = down;
  bool blink = (millis() / 500) % 2;
  digitalWrite(LED_PIN, (down || blink) ? HIGH : LOW);
  delay(10);
}
