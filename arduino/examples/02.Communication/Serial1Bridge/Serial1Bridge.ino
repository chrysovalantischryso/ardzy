/*
  Serial1Bridge: a real UART on the FPGA pins. TX = J1 pin 11, RX = J1 pin 12, 3.3 V.
  Connect a GPS, an ESP32, another Arduino (5 V boards need a level shifter on RX).
  What arrives on Serial1 is shown in the Monitor; what you type is sent out.
*/
void setup() {
  Serial.begin(115200);
  Serial1.begin(9600);
  Serial.println("Serial1 bridge at 9600 baud");
}

void loop() {
  while (Serial1.available()) Serial.write(Serial1.read());
  while (Serial.available()) Serial1.write(Serial.read());
}
