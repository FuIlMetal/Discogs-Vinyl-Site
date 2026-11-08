// Drives the shelf LED strip for the Vinyl site. The Pi sends one command per line over USB:
//   S <bgR> <bgG> <bgB> <start> <count> <r> <g> <b> [<start2> <count2> <r2> <g2> <b2>]
// which fills the strip with the background, paints <count> LEDs from <start>, optionally paints a
// second range on top, and replies OK or ERR.
// The Pi waits for that reply before sending more, because serial data is lost while show() runs.
#include <FastLED.h>

#define DATA_PIN 6
#define MAX_LEDS 300          // Must match LED_COUNT on the Pi. Fits the Uno's RAM; extra unused LEDs are harmless.
#define MAX_MILLIAMPS 5000    // Stays well inside a 5V 10A supply and limits heat on the shelf.

CRGB leds[MAX_LEDS];

bool validRange(int start, int count) {
  return start >= 0 && start < MAX_LEDS && count >= 0 && count <= MAX_LEDS;
}

void paintRange(int start, int count, int r, int g, int b) {
  for (int i = start; i < start + count && i < MAX_LEDS; i++) {
    leds[i] = CRGB(r, g, b);
  }
}

void setup() {
  FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, MAX_LEDS);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MILLIAMPS);
  FastLED.clear(true);
  Serial.begin(115200);
  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) return;

  char line[64];
  size_t length = Serial.readBytesUntil('\n', line, sizeof(line) - 1);
  line[length] = '\0';

  int bgR, bgG, bgB, start, count, r, g, b, start2, count2, r2, g2, b2;
  int fields = sscanf(line, "S %d %d %d %d %d %d %d %d %d %d %d %d %d", &bgR, &bgG, &bgB, &start, &count, &r, &g, &b,
                      &start2, &count2, &r2, &g2, &b2);
  bool valid = (fields == 8 || fields == 13) && validRange(start, count) && (fields == 8 || validRange(start2, count2));
  if (!valid) {
    Serial.println("ERR");
    return;
  }

  fill_solid(leds, MAX_LEDS, CRGB(bgR, bgG, bgB));
  paintRange(start, count, r, g, b);
  if (fields == 13) {
    paintRange(start2, count2, r2, g2, b2);
  }
  FastLED.show();
  Serial.println("OK");
}
