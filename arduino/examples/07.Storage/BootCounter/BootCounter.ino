/*
  BootCounter: EEPROM keeps a number across programs and power cycles (stored on the SD card).
*/
#include <EEPROM.h>

void setup() {
  Serial.begin(115200);
  unsigned long starts = 0;
  EEPROM.get(0, starts);
  if (starts == 0xFFFFFFFF) starts = 0;   // a new EEPROM is full of 0xFF
  starts++;
  EEPROM.put(0, starts);
  EEPROM.commit();
  Serial.print("This sketch has started ");
  Serial.print(starts);
  Serial.println(" time(s)");
}

void loop() {
}
