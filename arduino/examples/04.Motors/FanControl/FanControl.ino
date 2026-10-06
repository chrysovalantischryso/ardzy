/*
  FanControl: the board's 6 fan headers. The fans follow the chip temperature and their speed
  is printed (Plotter friendly).
*/
void setup() {
  Serial.begin(115200);
}

void loop() {
  float t = Ardzy.temperature();
  int duty = constrain(map((long)t, 40, 70, 20, 100), 20, 100);
  Ardzy.fan(duty);
  Serial.print("temperature:");
  Serial.print(t, 1);
  Serial.print(" duty:");
  Serial.print(duty);
  Serial.print(" fan1_rpm:");
  Serial.println(Ardzy.fanRpm(1));
  delay(1000);
}
