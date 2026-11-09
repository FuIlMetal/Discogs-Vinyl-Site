"""Talks to the Arduino that drives the shelf LEDs (see arduino/vinyl_leds and LED_SETUP.md)."""
import colorsys
import glob
import io
import threading

import requests
import serial
from PIL import Image

from discogs_api import get_led_brightness, get_led_settings

LED_COUNT = 300      # Most LEDs the site can address. Must match MAX_LEDS in the sketch. Set the real ends in /admin.
BAUD_RATE = 115200   # Must match the sketch
SPOT_WIDTH = 3       # LEDs lit to mark a record
SPIN_SECONDS = 4     # Must match SPIN_MS in the sketch
PUT_AWAY_COLOR = (255, 90, 0)  # Orange marks where the last played record goes back
WARM_WHITE = (255, 170, 90)  # Glow for covers with no real color, like black and white sleeves
OFF = (0, 0, 0)
MAX_WAVE_COLORS = 4  # Most the sketch accepts

_lock = threading.RLock()
_port = None
_ambient = None  # Colors the whole strip returns to (one = solid, more = wave), or None for off
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


def _command(line):
    """Send one command line. Returns False instead of raising, so missing hardware never breaks the site."""
    with _lock:
        try:
            if not _open_port():
                return False
            _port.reset_input_buffer()
            # While a wave animates, bytes sent during show() are lost. A lone wake byte survives in the
            # UART, and the Uno answers R and stops animating until it has read the command.
            _port.timeout = 0.3
            for _ in range(10):
                _port.write(b"!")
                if _port.readline().strip() == b"R":
                    break
            else:
                raise serial.SerialException("Arduino didn't answer the wake byte")
            _port.timeout = 3
            _port.write(line.encode())
            if _port.readline().strip() == b"OK":
                return True
            print(f"LED: Arduino didn't confirm: {line.strip()}")
        except Exception as e:  # Not just SerialException: a vanished Uno can raise termios.error, which would 500 every Find until restart
            print(f"LED: serial error: {e!r}")
        _close_port()  # Reconnect on the next command, in case it was unplugged
        return False


def _send(background, ranges=((0, 0, OFF),), spin=None):
    """Fill the strip with background and paint up to two (start, count, color) ranges on top.
    With spin=(first, last), a streak laps those LEDs first and lands on the last range."""
    fields = [*spin, *background] if spin else [*background]
    for start, count, color in ranges:
        fields += [start, count, *color]
    return _command(("P " if spin else "S ") + " ".join(map(str, fields)) + "\n")


def _show_glow():
    if _ambient is None:
        return _send(OFF)
    colors = [_scale(c, get_led_brightness() / 100) for c in _ambient[:MAX_WAVE_COLORS]]
    if len(colors) == 1:
        return _send(colors[0])
    fields = [get_led_settings()["wave_speed"]] + [v for c in colors for v in c]
    return _command("W " + " ".join(map(str, fields)) + "\n")


def _start_new_scene():
    """Whatever was showing is being replaced, so its pending timer must not fire."""
    global _generation, _timer
    _generation += 1
    if _timer:
        _timer.cancel()
        _timer = None


def set_ambient(colors=None):
    """Glow the whole strip at the saved brightness: one color is solid, more make a slow wave. None is off."""
    global _ambient
    with _lock:
        _start_new_scene()
        _ambient = colors
        return _show_glow()


def get_ambient():
    return _ambient


def show_spots(find=None, put_away=None, spin=False):
    """Light only these spots for the saved time, with everything else off, then go back to any glow.
    spin=True first sweeps a streak across the shelf that slows down onto the find spot."""
    global _timer

    def spot(led, color):
        return max(0, min(LED_COUNT - SPOT_WIDTH, led - SPOT_WIDTH // 2)), SPOT_WIDTH, color

    def restore(generation):
        with _lock:
            if generation == _generation:
                _show_glow()

    settings = get_led_settings()
    ranges = []
    if put_away is not None:
        ranges.append(spot(put_away, PUT_AWAY_COLOR))
    if find is not None:  # Painted last, so the find color wins if the two spots overlap
        ranges.append(spot(find, tuple(bytes.fromhex(settings["find_color"][1:]))))

    with _lock:
        _start_new_scene()
        seconds = settings["spot_seconds"]
        if spin and find is not None:
            last_led = LED_COUNT - 1 if settings["last_led"] is None else settings["last_led"]
            ok = _send(OFF, ranges, spin=(settings["first_led"], last_led))
            seconds += SPIN_SECONDS
        else:
            ok = _send(OFF, ranges)
        _timer = threading.Timer(seconds, restore, args=(_generation,))
        _timer.daemon = True
        _timer.start()
        return ok


def cover_colors(image, count=3):
    """Up to count eye-catching, different colors from an image, at full strength so they show up on LEDs."""
    palette = image.convert("RGB").resize((64, 64)).quantize(8).convert("RGB")
    scored = []
    for pixels, (r, g, b) in palette.getcolors():
        hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if saturation >= 0.2 and value > 0:
            scored.append((pixels * saturation * value, hue, saturation))
    picked = []
    for _, hue, saturation in sorted(scored, reverse=True):
        # Skip near-duplicate hues (hue wraps around, so red at 0.98 sits next to red at 0.02)
        if all(min(abs(hue - h), 1 - abs(hue - h)) > 0.06 for h, _ in picked):
            picked.append((hue, saturation))
        if len(picked) == count:
            break
    # LEDs wash pale colors out to white, so muted covers (lo-fi, pastels) get their saturation pushed up
    colors = [tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, 0.7 + 0.3 * (s - 0.2) / 0.8, 1))
              for h, s in picked] or [WARM_WHITE]
    if len(colors) == 1:  # One color still gets a gentle wave, into a dim version of itself
        colors.append(_scale(colors[0], 0.3))
    return colors


def cover_wave(url):
    """Wave colors for a cover image URL, or a warm white wave if it can't be loaded."""
    try:
        response = requests.get(url, headers={"User-Agent": "VinylPi/1.0"}, timeout=5)
        response.raise_for_status()
        return cover_colors(Image.open(io.BytesIO(response.content)))
    except (requests.RequestException, OSError) as e:
        print(f"LED: couldn't read cover {url!r}: {e}")
        return cover_colors(Image.new("RGB", (1, 1)))


if __name__ == "__main__":
    # Self-check: python led_controller.py
    half_red = Image.new("RGB", (64, 64), (10, 10, 10))
    half_red.paste((200, 20, 20), (0, 0, 64, 32))
    (r, g, b), dim = cover_colors(half_red)
    assert r == 255 and g < 60 and b < 60 and dim == _scale((r, g, b), 0.3), (r, g, b, dim)
    grey = Image.new("RGB", (64, 64), (128, 128, 128))
    assert cover_colors(grey) == cover_colors(Image.new("RGB", (64, 64))) == [WARM_WHITE, _scale(WARM_WHITE, 0.3)]
    stripes = Image.new("RGB", (64, 64), (200, 20, 20))
    stripes.paste((20, 20, 200), (0, 0, 64, 20))
    stripes.paste((20, 200, 20), (0, 20, 64, 30))
    stripes.paste((210, 30, 25), (0, 30, 64, 36))  # Near-duplicate red is skipped
    colors = cover_colors(stripes)
    assert len(colors) == 3 and colors[0][0] == 255 and colors[1][2] == 255 and colors[2][1] == 255, colors
    assert _scale((255, 100, 0), 0.5) == (127, 50, 0)
    assert cover_wave("") == [WARM_WHITE, _scale(WARM_WHITE, 0.3)]

    class FakePort:
        """Answers each wake byte with R (after dropping the first `lost` of them), then replies in order."""
        def __init__(self, replies, lost=0):
            self.replies, self.lines, self.pending, self.lost, self.timeout = list(replies), [], [], lost, 3
        def readline(self):
            return self.pending.pop(0) if self.pending else b""
        def reset_input_buffer(self):
            self.pending = []
        def write(self, data):
            if data == b"!":
                if self.lost:
                    self.lost -= 1
                else:
                    self.pending.append(b"R\r\n")
            else:
                self.lines.append(data.decode())
                self.pending.append(self.replies.pop(0))
        def close(self):
            pass

    get_led_brightness = lambda: 50
    get_led_settings = lambda: {"spot_seconds": 60, "find_color": "#ffffff", "wave_speed": 3, "first_led": 5, "last_led": None}
    _port = fake = FakePort([b"OK\r\n"] * 7 + [b"ERR\r\n"], lost=2)  # Lost wake bytes are retried
    assert set_ambient([(200, 100, 0)])
    assert fake.lines[-1] == "S 100 50 0 0 0 0 0 0\n"
    assert set_ambient([(200, 100, 0), (0, 0, 255), (10, 20, 30), (1, 1, 1), (2, 2, 2)])  # Wave, capped at 4 colors
    assert fake.lines[-1] == "W 3 100 50 0 0 0 127 5 10 15 0 0 0\n"
    longest = "W 10" + " 255" * 12 + "\n"
    assert len(longest) < 64  # Longest command has to fit the sketch's line buffer
    assert show_spots(find=0)  # Clamped to the start of the strip, with the glow off
    assert fake.lines[-1] == "S 0 0 0 0 3 255 255 255\n"
    assert show_spots(find=50, put_away=20)  # White is painted last, so it wins an overlap
    assert fake.lines[-1] == "S 0 0 0 19 3 255 90 0 49 3 255 255 255\n"
    assert show_spots(put_away=20) and fake.lines[-1] == "S 0 0 0 19 3 255 90 0\n"
    assert len("S 255 255 255 297 3 255 90 0 297 3 255 255 255\n") < 64
    assert set_ambient(None) and fake.lines[-1] == "S 0 0 0 0 0 0 0 0\n"
    assert show_spots(find=50, put_away=20, spin=True)
    assert fake.lines[-1] == f"P 5 {LED_COUNT - 1} 0 0 0 19 3 255 90 0 49 3 255 255 255\n", fake.lines[-1]
    assert _timer.interval == 60 + SPIN_SECONDS
    assert len(f"P 299 299 255 255 255 297 3 255 90 0 297 3 255 255 255\n") < 64
    assert not show_spots(find=LED_COUNT - 1) and fake.lines[-1].split()[4] == str(LED_COUNT - SPOT_WIDTH)
    assert _port is None  # A bad reply drops the port so the next command reconnects
    _port = FakePort([], lost=99)
    assert not set_ambient(None) and _port is None  # Never answers the wake byte: give up, reconnect later
    print("led_controller self-check OK")
