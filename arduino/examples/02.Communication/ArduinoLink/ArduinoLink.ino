/*
  ArduinoLink: Ardzy and an Arduino Uno / Nano / Mega talk over UART.

  What it does:
    The Arduino reads a sensor (here: its analog pin A0) and sends "a0:512" lines. Ardzy shows the
    value in the Monitor, on the Plotter and in the Watch tab, and answers "led:1" / "led:0" so the
    Arduino's own LED follows Ardzy's IP button.

  You need:
    an Arduino Uno (or Nano, Mega: any 5 V Arduino), 2 resistors (1 kOhm and 2 kOhm, or 10k + 20k),
    3 wires. A potentiometer on A0 if you want to turn something.

  IMPORTANT: the Arduino is a 5 V board, Ardzy's pins are 3.3 V and have no protection.
    Never connect the Arduino's TX straight to Ardzy: a voltage divider (or a level shifter module)
    brings 5 V down to 3.3 V.

  Wiring:
    Arduino TX (pin 1) ---[ 1k ]---+---> J1 pin 12 (Ardzy RX)
                                   |
                                 [ 2k ]
                                   |
                                  GND
    Arduino RX (pin 0) <------------------ J1 pin 11 (Ardzy TX)   (3.3 V is a HIGH for the Arduino)
    Arduino GND        ------------------- J1 pin 9 (GND)
    No wire between the 5V pins: each board has its own power.

  The Arduino's sketch (upload it with the Arduino IDE first; unplug the wire from Arduino pin 0
  while uploading, the Arduino's USB uses the same pin):

    void setup() { Serial.begin(9600); pinMode(LED_BUILTIN, OUTPUT); }
    void loop() {
      Serial.print("a0:"); Serial.println(analogRead(A0));
      while (Serial.available()) {
        String s = Serial.readStringUntil('\n');
        if (s.startsWith("led:")) digitalWrite(LED_BUILTIN, s.charAt(4) == '1');
      }
      delay(100);
    }

  Try:
    Turn the potentiometer and watch "a0" on the Plotter. Press the IP button: the Arduino's LED lights.
*/

String line;
int lastButton = -1;

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600);                          // the same speed as the Arduino's Serial.begin()
  Serial.println("Waiting for lines like a0:512 from the Arduino on J1 pin 12 ...");
}

void loop() {
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n') {
      line.trim();
      int colon = line.indexOf(':');
      if (colon > 0) {
        String name = line.substring(0, colon);
        long value = line.substring(colon + 1).toInt();
        Ardzy.watch(name.c_str(), value);      // the Watch tab and the Plotter
      }
      line = "";
    } else if (c != '\r' && line.length() < 60) {
      line += c;
    }
  }
  int b = digitalRead(BUTTON_IP) == LOW;       // the IP button reads LOW while pressed
  if (b != lastButton) {
    Serial1.print("led:");
    Serial1.println(b);
    lastButton = b;
  }
}
