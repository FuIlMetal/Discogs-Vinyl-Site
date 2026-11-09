# Shelf LED Setup

An Arduino Uno drives a WS2812B strip under the shelf above the records. The Pi sends it commands over USB.

- **Find on Shelf** turns off all other lights and lights the record's spot (white for 60 seconds unless changed under **Find light** in `/admin`). The last played record's spot lights in orange, showing where it goes back.
- **🎲 Random Record** shuffles covers on screen like a jukebox while a streak spins across the shelf. Both slow down and land on the chosen record together, then it shows like Find.
- **Adding a record** says which records it goes between and spins the lights onto its spot.
- **✕ on the Now Spinning banner** lights where the record goes back in orange.
- **Album wave** is off by default. Turn it on in `/admin` to make a slow wave of 2–3 colors from the cover scroll along the strip while a record plays. Set its speed under **Find light**.
- **/admin** (Tailscale only) has on/off, color, brightness and album glow controls, the shelf order, and spot checking.

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

On the Pi, with the Uno plugged in:

```bash
cd ~/Vinyl-site/discogs-vinyl-site
bash deploy/flash-arduino.sh
```

The first run installs `arduino-cli`, the Uno board files and FastLED, which takes a few minutes. The site pauses for the upload and starts again on its own. Run it again whenever the sketch changes.

## Set up the Pi

Plug the Uno into the Pi, then let the service use the serial port. This only needs doing once:

```bash
sudo usermod -aG dialout fullmetal
sudo systemctl restart discogs-vinyl-site.service
```

The auto-updater installs the Python packages. No nginx change is needed.

## Sort and check the shelf

1. In `/admin` under **Find light**, step **Strip starts at LED** and **ends at LED** until the lit LED sits over the first and last record slot, then **Save**. Records without a saved spot stay inside that range.
2. The table starts in shelf order, and **#** is each record's place from left to right. Shelve the records in that order.
3. Tap the **first** record on the shelf. Use ◀ ▶ to move the light onto it, then **Save spot**. Do the same for the **last** record.
4. Do the same for about every 10th record in between. Records between saved spots are spaced evenly.
5. Tap any record to check where its light lands.

Order is by the artist name exactly as Discogs writes it, the same as the home page, so The Beatles file under T and Miles Davis under M.

The site can address up to 300 LEDs. Set where your strip really starts and ends with the Find light settings in step 1. For a strip longer than 300, raise `LED_COUNT` in `led_controller.py` and `MAX_LEDS` in the sketch to match, then flash the Uno again.

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
