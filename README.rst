CircuitPython Library for Waveshare 1.9" Segment E-Ink Display
==============================================================

This display is extraordinary in a few ways:

  - it uses I2C instead of SPI
  - it is a /segment/ display with 92 segments  
    (individual pixels are not addressable)
  - it can only display temperature and humidity and a few symbols
  - only a 15 byte large data-buffer is needed

Waveshare provides some basic code for C/C++ and Python, but no
user-level driver.

This CircuitPython driver fills the gap. Usage is simple:

```
from e_ink_seg_display import SegmentDisplay
import adafruit_ahtx0

display = SegmentDisplay(i2c,rst_pin=PIN_RST,busy_pin=PIN_BUSY)
display.init()
display.update_mode(full=False)
display.clear()

aht20 = adafruit_ahtx0.AHTx0(i2c)

while True:
  display.set_temperature(aht20.temperature)
  display.set_humidity(aht20.relative_humidity)
  display.update()
  time.sleep(INTERVAL)
```

Porting to other languages (e.g. MicroPython or C/C++) should be simple,
since access to hardware-objects (I2C and GPIOs) is only in a few methods.
