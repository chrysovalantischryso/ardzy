/*
  SerialPlotter: prints numbers as "name:value" pairs. Open the Plotter tab next to the Monitor.
*/
float t = 0;

void setup() {
  Serial.begin(115200);
}

void loop() {
  Serial.print("sine:");
  Serial.print(sin(t) * 100);
  Serial.print(" cosine:");
  Serial.print(cos(t) * 50);
  Serial.print(" temperature:");
  Serial.println(Ardzy.temperature());
  t += 0.1;
  delay(50);
}
