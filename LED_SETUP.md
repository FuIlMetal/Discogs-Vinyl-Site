# Shelf LED Setup

An Arduino Uno drives a WS2812B strip under the shelf above the records. The Pi sends it commands over USB.

- **Find on Shelf** on any record lights its spot for 60 seconds.
- **Let's Play This** glows the whole strip in the album cover's color.
- **✕ on the Now Spinning banner** turns off the glow and lights where the record goes back.
- **/admin** (Tailscale only) has on/off, color and brightness controls, the shelf order, and spot checking.

## Parts

- WS2812B strip, 5V, 144 LEDs/m, 1 m, non-waterproof (IP30). Cut to 28in, about 102 LEDs, on the marked line across the copper pads.
- 5V 10A power supply, with a screw terminal adapter that fits its plug
- 470–1000 µF capacitor, rated 6.3V or higher
- 330–470 Ω resistor
- Aluminum channel with a diffuser, for mounting

## Wiring

⚠️ Never connect the Uno's 5V pin to the strip or the power supply. Two 5V sources can damage the Uno and the Pi.

| From | To |
|---|---|
| Supply + | Strip 5V |
| Supply − | Strip GND **and** Uno GND |
| Uno pin 6 | Resistor, then strip DIN (resistor close to the strip) |
| Capacitor + and − | Strip 5V and GND, at the supply end. Match the polarity. |
| Uno USB | Pi USB port, which powers the Uno |

Data only flows one way, so connect to the end where the strip's arrows point away. Mount that end on the left, so LED 0 is the far left of the shelf.

## Mounting

Fix the channel near the front edge of the underside of the shelf above, so the light lands on the spines. Keep boxes and anything else off the tops of the records, because they block the light.

## Flash the Arduino

From any computer with the [Arduino IDE](https://www.arduino.cc/en/software):

1. Install the **FastLED** library (Tools → Manage Libraries).
2. Open `arduino/vinyl_leds/vinyl_leds.ino`.
3. Select **Arduino Uno**, then upload.

## Set up the Pi

Plug the Uno into the Pi, then let the service use the serial port. This only needs doing once:

```bash
sudo usermod -aG dialout fullmetal
sudo systemctl restart discogs-vinyl-site.service
```

The auto-updater installs the Python packages. No nginx change is needed.

## Sort and check the shelf

1. Open `/admin`. The table starts in shelf order, and **#** is each record's place from left to right. Shelve the records in that order.
2. Tap the **first** record on the shelf. Use ◀ ▶ to move the light onto it, then **Save spot**. Do the same for the **last** record.
3. Do the same for about every 10th record in between. Records between saved spots are spaced evenly.
4. Tap any record to check where its light lands.

Order is by the artist name exactly as Discogs writes it, the same as the home page, so The Beatles file under T and Miles Davis under M.

If you cut the strip to a different length, change `LED_COUNT` in `led_controller.py`.

## Self-checks

```bash
venv/bin/python shelf.py
venv/bin/python led_controller.py
```

## Troubleshooting

"The shelf lights aren't connected" means the site can't talk to the Uno:

- Run `ls /dev/ttyACM* /dev/ttyUSB*` to check that the Pi can see the Uno.
- Run `groups fullmetal` to check for `dialout`, then restart the service.
- Run `sudo journalctl -u discogs-vinyl-site.service -n 50` and look for lines starting `LED:`.

If the site says the lights are working but nothing lights up, check the shared ground, the supply, and that data goes into DIN and not DOUT.
