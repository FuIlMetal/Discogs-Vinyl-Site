"""Talks to the Arduino that drives the shelf LEDs (see arduino/vinyl_leds and LED_SETUP.md)."""
import colorsys
import glob
import io
import threading

import requests
import serial
from PIL import Image

from discogs_api import get_led_brightness

LED_COUNT = 102      # LEDs in use: 28in of shelf on a 144 LEDs/m strip. Change this if you cut it differently.
BAUD_RATE = 115200   # Must match the sketch
SPOT_WIDTH = 3       # LEDs lit to mark a record
SPOT_SECONDS = 60    # How long a marked spot stays lit
FIND_COLOR = (255, 255, 255)
PUT_AWAY_COLOR = (255, 90, 0)  # Orange marks where the last played record goes back
WARM_WHITE = (255, 170, 90)  # Glow for covers with no real color, like black and white sleeves
OFF = (0, 0, 0)

_lock = threading.RLock()
_port = None
_ambient = None  # Color the whole strip returns to, or None for off
_timer = None
_generation = 0  # Lets a spot timer that already fired notice it's out of date


def _close_port():
    global _port
    if _port:
        try:
            _port.close()
        except (serial.SerialException, OSError):
            pass
    _port = None


def _open_port():
    global _port
    if _port:
        return True
    # Uno R3s show up as ttyACM*, clones as ttyUSB*. The number can change after a replug.
    ports = sorted(glob.glob("/dev/ttyACM*")) + sorted(glob.glob("/dev/ttyUSB*"))
    if not ports:
        return False
    _port = serial.Serial(ports[0], BAUD_RATE, timeout=3)
    _port.readline()  # Opening the port reboots the Uno, so wait for READY (or the timeout)
    return True


def _scale(color, factor):
    return tuple(int(c * factor) for c in color)


def _send(background, ranges=((0, 0, OFF),)):
    """Update the strip. Returns False instead of raising, so missing hardware never breaks the site."""
    fields = [*background]
    for start, count, color in ranges:
        fields += [start, count, *color]
    line = "S " + " ".join(map(str, fields)) + "\n"
    with _lock:
        try:
            if not _open_port():
                return False
            _port.reset_input_buffer()
            _port.write(line.encode())
            if _port.readline().strip() == b"OK":
                return True
            print(f"LED: Arduino didn't confirm: {line.strip()}")
        except Exception as e:  # Not just SerialException: a vanished Uno can raise termios.error, which would 500 every Find until restart
            print(f"LED: serial error: {e!r}")
        _close_port()  # Reconnect on the next command, in case it was unplugged
        return False


def _glow_color():
    if _ambient is None:
        return OFF
    return _scale(_ambient, get_led_brightness() / 100)


def _start_new_scene():
    """Whatever was showing is being replaced, so its pending timer must not fire."""
    global _generation, _timer
    _generation += 1
    if _timer:
        _timer.cancel()
        _timer = None


def set_ambient(color=None):
    """Glow the whole strip in color at the saved brightness, or turn it off with None."""
    global _ambient
    with _lock:
        _start_new_scene()
        _ambient = color
        return _send(_glow_color())


def get_ambient():
    return _ambient


def show_spots(find=None, put_away=None):
    """Light only these spots for SPOT_SECONDS, with everything else off, then go back to any glow."""
    global _timer

    def spot(led, color):
        return max(0, min(LED_COUNT - SPOT_WIDTH, led - SPOT_WIDTH // 2)), SPOT_WIDTH, color

    def restore(generation):
        with _lock:
            if generation == _generation:
                _send(_glow_color())

    ranges = []
    if put_away is not None:
        ranges.append(spot(put_away, PUT_AWAY_COLOR))
    if find is not None:  # Painted last, so white wins if the two spots overlap
        ranges.append(spot(find, FIND_COLOR))

    with _lock:
        _start_new_scene()
        ok = _send(OFF, ranges)
        _timer = threading.Timer(SPOT_SECONDS, restore, args=(_generation,))
        _timer.daemon = True
        _timer.start()
        return ok


def dominant_color(image):
    """The most eye-catching main color of an image, at full strength so it shows up on LEDs."""
    palette = image.convert("RGB").resize((64, 64)).quantize(8).convert("RGB")
    best_score, best_hue, best_saturation = 0, 0, 0
    for pixels, (r, g, b) in palette.getcolors():
        hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        score = pixels * saturation * value
        if score > best_score:
            best_score, best_hue, best_saturation = score, hue, saturation
    if best_saturation < 0.2:
        return WARM_WHITE
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(best_hue, best_saturation, 1))


def cover_color(url):
    """Color for a cover image URL, or warm white if it can't be loaded."""
    try:
        response = requests.get(url, headers={"User-Agent": "VinylPi/1.0"}, timeout=5)
        response.raise_for_status()
        return dominant_color(Image.open(io.BytesIO(response.content)))
    except (requests.RequestException, OSError) as e:
        print(f"LED: couldn't read cover {url!r}: {e}")
        return WARM_WHITE


if __name__ == "__main__":
    # Self-check: python led_controller.py
    half_red = Image.new("RGB", (64, 64), (10, 10, 10))
    half_red.paste((200, 20, 20), (0, 0, 64, 32))
    r, g, b = dominant_color(half_red)
    assert r == 255 and g < 60 and b < 60, (r, g, b)
    assert dominant_color(Image.new("RGB", (64, 64), (128, 128, 128))) == WARM_WHITE
    assert dominant_color(Image.new("RGB", (64, 64), (0, 0, 0))) == WARM_WHITE
    assert _scale((255, 100, 0), 0.5) == (127, 50, 0)
    assert cover_color("") == WARM_WHITE

    class FakePort:
        def __init__(self, replies):
            self.replies, self.lines = list(replies), []
        def readline(self):
            return self.replies.pop(0)
        def reset_input_buffer(self):
            pass
        def write(self, data):
            self.lines.append(data.decode())
        def close(self):
            pass

    get_led_brightness = lambda: 50
    _port = fake = FakePort([b"OK\r\n", b"OK\r\n", b"OK\r\n", b"OK\r\n", b"ERR\r\n"])
    assert set_ambient((200, 100, 0))
    assert fake.lines[-1] == "S 100 50 0 0 0 0 0 0\n"
    assert show_spots(find=0)  # Clamped to the start of the strip, with the glow off
    assert fake.lines[-1] == "S 0 0 0 0 3 255 255 255\n"
    assert show_spots(find=50, put_away=20)  # White is painted last, so it wins an overlap
    assert fake.lines[-1] == "S 0 0 0 19 3 255 90 0 49 3 255 255 255\n"
    assert show_spots(put_away=20) and fake.lines[-1] == "S 0 0 0 19 3 255 90 0\n"
    assert len(fake.lines[-2]) < 64  # Longest command has to fit the sketch's line buffer
    assert not show_spots(find=LED_COUNT - 1) and fake.lines[-1].split()[4] == str(LED_COUNT - SPOT_WIDTH)
    assert _port is None  # A bad reply drops the port so the next command reconnects
    _timer.cancel()
    print("led_controller self-check OK")
