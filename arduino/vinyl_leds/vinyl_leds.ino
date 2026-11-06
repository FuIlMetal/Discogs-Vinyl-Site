// Drives the shelf LED strip for the Vinyl site. The Pi sends one command per line over USB:
//   S <bgR> <bgG> <bgB> <start> <count> <r> <g> <b>
// which fills the strip with the background, paints <count> LEDs from <start>, and replies OK or ERR.
// The Pi waits for that reply before sending more, because serial data is lost while show() runs.
#include <FastLED.h>

#define DATA_PIN 6
#define MAX_LEDS 144          // Whole uncut 1m strip. The Pi decides how many are really in use.
#define MAX_MILLIAMPS 5000    // Stays well inside a 5V 10A supply and limits heat on the shelf.

CRGB leds[MAX_LEDS];

void setup() {
  FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, MAX_LEDS);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MILLIAMPS);
  FastLED.clear(true);
  Serial.begin(115200);
  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) return;

  char line[48];
  size_t length = Serial.readBytesUntil('\n', line, sizeof(line) - 1);
  line[length] = '\0';

  int bgR, bgG, bgB, start, count, r, g, b;
  int fields = sscanf(line, "S %d %d %d %d %d %d %d %d", &bgR, &bgG, &bgB, &start, &count, &r, &g, &b);
  if (fields != 8 || start < 0 || start >= MAX_LEDS || count < 0 || count > MAX_LEDS) {
    Serial.println("ERR");
    return;
  }

  fill_solid(leds, MAX_LEDS, CRGB(bgR, bgG, bgB));
  for (int i = start; i < start + count && i < MAX_LEDS; i++) {
    leds[i] = CRGB(r, g, b);
  }
  FastLED.show();
  Serial.println("OK");
}
