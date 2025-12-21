import os
try:
    from rpi_ws281x import PixelStrip, Color
    WS281X_AVAILABLE = True
except ImportError:
    # Library not available (e.g., on Windows or not installed)
    WS281X_AVAILABLE = False
    print("rpi-ws281x not available - LED functionality disabled")

# LED strip configuration
LED_COUNT = 144        # Number of LED pixels (1m strip with 144 LEDs/m = 144 LEDs total)
LED_PIN = 10          # GPIO pin connected to the pixels (10 = SPI0 MOSI, recommended for WS2812B)
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10          # DMA channel to use for generating signal
LED_BRIGHTNESS = 77   # Set to 0 for darkest and 255 for brightest (30% = ~77)
LED_INVERT = False    # True to invert the signal
LED_CHANNEL = 0       # Set to '1' for GPIOs 13, 19, 41, 45 or 53

# Initialize strip (None if not on Raspberry Pi)
strip = None

def init_led_strip():
    """Initialize the LED strip. Returns True if successful."""
    global strip
    if not WS281X_AVAILABLE:
        return False
    try:
        # Only initialize on Raspberry Pi
        if os.path.exists('/proc/device-tree/model'):
            strip = PixelStrip(
                LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, 
                LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
            )
            strip.begin()
            return True
        else:
            print("Not running on Raspberry Pi - LED strip disabled")
            return False
    except Exception as e:
        print(f"Error initializing LED strip: {e}")
        return False

def set_all_leds(brightness_percent=30):
    """
    Set all LEDs to a specific brightness (0-100%).
    Returns True if successful.
    """
    global strip
    
    if strip is None:
        if not init_led_strip():
            return False
    
    try:
        # Convert percentage to 0-255 range
        brightness = int((brightness_percent / 100.0) * 255)
        brightness = max(0, min(255, brightness))  # Clamp to valid range
        
        # Set all pixels to white at specified brightness
        color = Color(brightness, brightness, brightness)
        
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, color)
        
        strip.show()
        return True
    except Exception as e:
        print(f"Error setting LEDs: {e}")
        return False

def clear_leds():
    """Turn off all LEDs."""
    global strip
    
    if strip is None:
        return False
    
    try:
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
        return True
    except Exception as e:
        print(f"Error clearing LEDs: {e}")
        return False

