/*
  AnalogReadSerial: the board has no analog pins on its connectors, but the chip measures its
  own temperature and supply voltages. A0 = temperature, A1..A6 = voltages (raw, 0..1023).
  Open the Plotter to see the numbers as a graph.
*/
void setup() {
  Serial.begin(115200);
}

void loop() {
  int raw = analogRead(A0);
  Serial.print("raw:");
  Serial.print(raw);
  Serial.print(" celsius:");
  Serial.println(Ardzy.temperature(), 1);
  delay(500);
}
