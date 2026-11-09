// Drives the shelf LED strip for the Vinyl site. For each command the Pi sends a wake byte "!",
// waits for "R", then sends one line:
//   S <bgR> <bgG> <bgB> <start> <count> <r> <g> <b> [<start2> <count2> <r2> <g2> <b2>]
//     fills the strip with the background, paints <count> LEDs from <start>, optionally paints a
//     second range on top, and stops any wave.
//   W <speed 1-10> <r1> <g1> <b1> <r2> <g2> <b2> [<r3> <g3> <b3> [<r4> <g4> <b4>]]
//     slowly scrolls a wave blending 2 to 4 colors along the strip.
// and the Uno replies OK or ERR.
// Serial data is lost while show() runs, so the animation can drop a whole command line. A single
// wake byte survives in the UART's buffer, and once the Uno answers R it stops drawing until the line is in.
#include <FastLED.h>

#define DATA_PIN 6
#define MAX_LEDS 300          // Must match LED_COUNT on the Pi. Fits the Uno's RAM; extra unused LEDs are harmless.
#define MAX_MILLIAMPS 5000    // Stays well inside a 5V 10A supply and limits heat on the shelf.
#define FRAME_MS 33           // About 30 frames a second
#define WAVE_LEDS 50          // Length of one color fading into the next
#define SPEED_STEP 87         // Speed 1 moves the wave about 2 LEDs a second, speed 10 about 20

CRGB leds[MAX_LEDS];
CRGB waveColors[4];
uint8_t waveCount = 0;        // 0 = no wave
uint8_t waveSpeed = 3;
uint32_t wavePhase = 0;       // 65536 = one color's length
unsigned long lastFrame = 0;

bool validRange(int start, int count) {
  return start >= 0 && start < MAX_LEDS && count >= 0 && count <= MAX_LEDS;
}

void paintRange(int start, int count, int r, int g, int b) {
  for (int i = start; i < start + count && i < MAX_LEDS; i++) {
    leds[i] = CRGB(r, g, b);
  }
}

void drawWave() {
  const uint32_t cycle = (uint32_t)waveCount << 16;
  wavePhase = (wavePhase + (uint32_t)waveSpeed * SPEED_STEP) % cycle;
  for (int i = 0; i < MAX_LEDS; i++) {
    // Subtracting the phase moves the wave from LED 0 toward the end
    uint32_t t = ((uint32_t)i * (65536UL / WAVE_LEDS) + cycle - wavePhase) % cycle;
    uint8_t index = t >> 16;
    uint8_t fraction = ease8InOutQuad((t >> 8) & 0xFF);
    leds[i] = blend(waveColors[index], waveColors[(index + 1) % waveCount], fraction);
  }
  FastLED.show();
}

bool runCommand(char *line) {
  while (*line == '!') line++;  // A retried wake byte can land in front of the command

  int v[14];
  if (line[0] == 'S') {
    int fields = sscanf(line, "S %d %d %d %d %d %d %d %d %d %d %d %d %d", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5],
                        &v[6], &v[7], &v[8], &v[9], &v[10], &v[11], &v[12]);
    if (!((fields == 8 || fields == 13) && validRange(v[3], v[4]) && (fields == 8 || validRange(v[8], v[9])))) {
      return false;
    }
    waveCount = 0;
    fill_solid(leds, MAX_LEDS, CRGB(v[0], v[1], v[2]));
    paintRange(v[3], v[4], v[5], v[6], v[7]);
    if (fields == 13) {
      paintRange(v[8], v[9], v[10], v[11], v[12]);
    }
    FastLED.show();
    return true;
  }
  if (line[0] == 'W') {
    int fields = sscanf(line, "W %d %d %d %d %d %d %d %d %d %d %d %d %d", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5],
                        &v[6], &v[7], &v[8], &v[9], &v[10], &v[11], &v[12]);
    int colors = (fields - 1) / 3;
    if (fields < 7 || (fields - 1) % 3 != 0 || v[0] < 1 || v[0] > 10) {
      return false;
    }
    for (int c = 0; c < colors; c++) {
      waveColors[c] = CRGB(v[1 + c * 3], v[2 + c * 3], v[3 + c * 3]);
    }
    waveSpeed = v[0];
    waveCount = colors;
    drawWave();
    return true;
  }
  return false;
}

void setup() {
  FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, MAX_LEDS);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MILLIAMPS);
  FastLED.clear(true);
  Serial.begin(115200);
  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    delay(5);  // Let any repeated wake bytes arrive, then drop them
    while (Serial.available()) Serial.read();
    Serial.println("R");

    char line[64];
    size_t length = Serial.readBytesUntil('\n', line, sizeof(line) - 1);
    line[length] = '\0';
    if (length > 0) {
      Serial.println(runCommand(line) ? "OK" : "ERR");
    }
    lastFrame = millis();
    return;
  }

  if (waveCount > 0 && millis() - lastFrame >= FRAME_MS) {
    lastFrame = millis();
    drawWave();
  }
}
