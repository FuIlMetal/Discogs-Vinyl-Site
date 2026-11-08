#!/usr/bin/env bash
# Upload arduino/vinyl_leds to the Uno from the Pi: bash deploy/flash-arduino.sh
# Installs arduino-cli, the AVR core and FastLED the first time.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

CLI_VERSION=1.5.1
# Pick by the OS, not the kernel: 32-bit Pi OS often runs on a 64-bit kernel, and 64-bit tools can't run there
case "$(uname -m)/$(getconf LONG_BIT)" in
    x86_64/64) ARCH=64bit ;;
    aarch64/64) ARCH=ARM64 ;;
    *) ARCH=ARMv7 ;;
esac
MARKER="$HOME/.local/bin/.arduino-cli-arch"
if [ "$(cat "$MARKER" 2>/dev/null)" != "$CLI_VERSION/$ARCH" ]; then
    # Also drops boards and tools downloaded for the wrong architecture by an earlier install
    rm -rf "$HOME/.arduino15/packages" "$HOME/.local/bin/arduino-cli"
    mkdir -p "$HOME/.local/bin"
    curl -fsSL "https://downloads.arduino.cc/arduino-cli/arduino-cli_${CLI_VERSION}_Linux_${ARCH}.tar.gz" \
        | tar -xz -C "$HOME/.local/bin" arduino-cli
    echo "$CLI_VERSION/$ARCH" > "$MARKER"
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
