#!/usr/bin/env bash
# Upload arduino/vinyl_leds to the Uno from the Pi: bash deploy/flash-arduino.sh
# Installs arduino-cli, the AVR core and FastLED the first time.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

if ! command -v arduino-cli >/dev/null; then
    mkdir -p "$HOME/.local/bin"
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$HOME/.local/bin" sh
fi
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli lib install FastLED

PORT=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1 || true)
[ -n "$PORT" ] || { echo "No Arduino found. Is the Uno's USB plugged into the Pi?"; exit 1; }

# The site holds the serial port open, so pause it during the upload and always start it again
sudo systemctl stop discogs-vinyl-site.service
trap 'sudo systemctl start discogs-vinyl-site.service' EXIT
arduino-cli compile --upload --port "$PORT" --fqbn arduino:avr:uno arduino/vinyl_leds
echo "Uploaded to $PORT"
