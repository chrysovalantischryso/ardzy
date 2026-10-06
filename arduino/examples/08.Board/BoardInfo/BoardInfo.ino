/*
  BoardInfo: everything the board knows about itself.
*/
void setup() {
  Serial.begin(115200);
  Serial.print("Chip ID (DNA): ");   Serial.println(Ardzy.chipId());
  Serial.print("FPGA clock:    ");   Serial.print(Ardzy.fpgaClock() / 1e6, 2); Serial.println(" MHz");
  Serial.print("Temperature:   ");   Serial.print(Ardzy.temperature(), 1); Serial.println(" C");
  const char *rails[] = {"vccint", "vccaux", "vccbram", "vccpint", "vccpaux", "vccoddr"};
  for (const char *r : rails) {
    Serial.print(r); Serial.print(": "); Serial.print(Ardzy.voltage(r), 3); Serial.println(" V");
  }
  Serial.print("Pin control:   ");   Serial.println(Ardzy.pinControlLoaded() ? "loaded" : "not loaded");
  Ardzy.beep(50);
}

void loop() {
}
