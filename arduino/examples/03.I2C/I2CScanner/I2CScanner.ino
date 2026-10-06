/*
  I2CScanner: lists the I2C devices on bus 1 (pins 3 = SDA, 4 = SCL of J1..J8)
  and bus 2 (J9). The board has the pull-up resistors already.
*/
#include <Wire.h>

void scan(TwoWire &bus, const char *name) {
  int found = 0;
  for (int address = 1; address < 127; address++) {
    bus.beginTransmission(address);
    if (bus.endTransmission() == 0) {
      Serial.print(name);
      Serial.print(": device at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      found++;
    }
  }
  Serial.print(name);
  Serial.print(": ");
  Serial.print(found);
  Serial.println(" device(s)");
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire1.begin();
}

void loop() {
  scan(Wire, "bus 1 (J1..J8)");
  scan(Wire1, "bus 2 (J9)");
  delay(5000);
}
