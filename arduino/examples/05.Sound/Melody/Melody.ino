/*
  Melody: tone() on J6 pin 5 (connect a small passive buzzer or speaker with a 100 ohm resistor).
  The board's own buzzer only beeps: Ardzy.beep(ms).
*/
int notes[] = {262, 294, 330, 349, 392, 440, 494, 523};

void setup() {
  for (int i = 0; i < 8; i++) {
    tone(J6_5, notes[i], 200);
    delay(250);
  }
  Ardzy.beep(100);
}

void loop() {
}
