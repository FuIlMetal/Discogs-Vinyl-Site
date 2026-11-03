# LED Strip Setup Guide

This guide covers the setup and troubleshooting for the WS2812B LED strip integration.

## Hardware Setup

### LED Strip Specifications
- **Type**: WS2812B (144 LEDs/m, 1 meter = 144 LEDs total)
- **Voltage**: 5V DC
- **Data Protocol**: Single-wire addressable

### Wiring

Connect your LED strip to the Raspberry Pi:

1. **Power Supply** (External 5V):
   - **VCC (Red)** → 5V power supply positive
   - **GND (Black/White)** → Ground (shared between Pi and power supply)

2. **Data Line**:
   - **DIN (Green)** → **Physical Pin 19** on Raspberry Pi (GPIO 10)

3. **Important**: 
   - Use an external 5V power supply (not the Pi's 5V pin)
   - Connect Pi ground to power supply ground
   - For reliability, consider using a logic level shifter (3.3V Pi → 5V LEDs), though many setups work without one

### GPIO Pin Reference
- **GPIO 10** = Physical Pin 19
- This is SPI0 MOSI, recommended for WS2812B LEDs

## Software Setup

### 1. Install rpi-ws281x Library

```bash
# Activate your virtual environment
source venv/bin/activate

# Install the library
pip install rpi-ws281x
```

### 2. GPIO Permissions

The service may need GPIO access. If LEDs don't work, try:

```bash
# Add your user to the gpio group
sudo usermod -a -G gpio pi

# Or run the service as root (less secure, but works)
# Edit the service file:
sudo nano /etc/systemd/system/discogs-vinyl-site.service
# Change User=pi to User=root
```

### 3. Verify Installation

After deployment, test the LEDs:

```bash
# Check diagnostics
curl http://localhost:8080/api/leds/diagnostics

# Test LEDs
curl -X POST http://localhost:8080/api/leds/test
```

## Configuration

LED settings are in `led_controller.py`:

- `LED_COUNT = 144` - Number of LEDs (adjust if your strip is different)
- `LED_PIN = 10` - GPIO pin (10 = SPI0 MOSI, physical pin 19)
- `LED_BRIGHTNESS = 77` - Default brightness (77 = ~30% of 255)

## Troubleshooting

### LEDs Not Working

1. **Check Diagnostics Endpoint**:
   ```
   http://your-pi-ip/api/leds/diagnostics
   ```
   This will show:
   - Library installation status
   - Raspberry Pi detection
   - Initialization status
   - Configuration details
   - Specific error messages

2. **Check Service Logs**:
   ```bash
   sudo journalctl -u discogs-vinyl-site.service -f
   ```
   Look for "DEBUG:" messages that show what's happening.

3. **Common Issues**:

   - **Library not installed**: 
     ```bash
     pip install rpi-ws281x
     ```

   - **GPIO permissions**: 
     ```bash
     sudo usermod -a -G gpio pi
     sudo systemctl restart discogs-vinyl-site.service
     ```

   - **Wrong GPIO pin**: 
     - Verify physical pin 19 is connected to LED data line
     - Check `LED_PIN` in `led_controller.py`

   - **Hardware connection**:
     - Verify data line is on physical pin 19 (GPIO 10)
     - Check power supply is adequate (144 LEDs need ~8.6A at full brightness)
     - Ensure proper ground connection

   - **DMA channel conflict**:
     - Try changing `LED_DMA` in `led_controller.py` (try 5 or 6)

### Testing LEDs

1. **Via Web Interface**: Click "Let's Play This" on any record
2. **Via API**: 
   ```bash
   curl -X POST http://localhost:8080/api/leds/test
   ```
3. **Check Browser Console**: Open browser dev tools (F12) and check console for LED status

## Deployment Checklist

After pulling new code:

1. ✅ Run `./deploy.sh` (or manually: install deps, restart service)
2. ✅ Check service is running: `sudo systemctl status discogs-vinyl-site.service`
3. ✅ Test LEDs: Visit diagnostics endpoint or click "Let's Play This"
4. ✅ Check logs if issues: `sudo journalctl -u discogs-vinyl-site.service -n 50`

