/*
  Fade: analogWrite() makes a PWM signal (made by the FPGA, 1 kHz). LED0 fades in and out.
  Any connector pin can do PWM too (8 at the same time).
*/
int brightness = 0;
int step = 5;

void setup() {
  pinMode(LED0, OUTPUT);
}

void loop() {
  analogWrite(LED0, brightness);
  brightness += step;
  if (brightness <= 0 || brightness >= 255) step = -step;
  delay(30);
}
