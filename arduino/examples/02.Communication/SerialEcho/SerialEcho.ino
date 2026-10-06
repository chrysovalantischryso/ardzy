/*
  SerialEcho: type in the Monitor's input box and press Enter; the sketch answers.
*/
void setup() {
  Serial.begin(115200);
  Serial.println("Type something and press Enter");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    Serial.print("You typed: ");
    Serial.println(line);
    if (line == "beep") Ardzy.beep(100);
  }
}
