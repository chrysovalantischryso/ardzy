// WatchValues: shows values live in the app's Watch tab (bottom panel) and draws them on the Plotter.
// The board's Data logger (Board view) can also record them to the SD card, for hours, without the PC.
// Ardzy.watch(name, value) prints one line "name:value" (text: name="text").

int count = 0;

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_IP, INPUT);
}

void loop() {
  count++;
  Ardzy.watch("count", count);
  Ardzy.watch("temperature", Ardzy.temperature());
  Ardzy.watch("vccint", Ardzy.voltage("vccint"));
  Ardzy.watch("button", digitalRead(BUTTON_IP) == LOW ? "pressed" : "released");
  delay(500);
}
