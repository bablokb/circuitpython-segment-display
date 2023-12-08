# ----------------------------------------------------------------------------
# e_ink_seg_display.py: driver for Waveshare 1.9" e-ink segment display
#
# Author: Bernhard Bablok
# License: GPL3
#
# Website: https://github.com/bablokb/circuitpython-segment-display
#
# ----------------------------------------------------------------------------

import time
import digitalio
from adafruit_bus_device.i2c_device import I2CDevice

try:
    import typing  # pylint: disable=unused-import
except:
    pass

"""
Some technical stuff:

The driver-IC supports 120 segments, but the display only uses 92 of them.
It still needs 15 bytes, but not all bits are used.

There are 5 big and 2 small digits. Every digit (except the first, see below)
has 13 segments and uses 13 bits from two consecutive bytes. Bit-to-segment
mapping is top-down - left-right:

    5
 0 *-*0
 1 |6|1
 2 *-*2
 3 |7|3
 4 *-*4

The very first digit only supports the number "1" and uses bits 0-4 of byte 1.

Bytes
-----

    0: first digit
 1- 2: first full digit of temperature (normal height)
 3- 4: second full digit of temperature (normal height)
    4: 0x20: temperature radix-point
 5- 6: first full digit of humidity (normal height)
 7- 8: second full digit of humidity (normal height)
    8: 0x20: humidity radix-point
 9-10: third full digit of humidity (small height)
11-12: third full digit of temperature (small height)
   13: specials: temp-unit (0x05/0x06), BT (0x08), power (0x10), percent (0x20)
   14: unused
"""


class SegmentDisplay:
    """driver for Waveshare 1.9 e-ink segment display"""

    # constants
    _ADDR_COM = 0x3C
    _ADDR_DATA = 0x3D
    _NUMBERS = [
        [0xBF, 0x1F],  # 0
        [0x00, 0x1F],  # 1
        [0xFD, 0x17],  # 2
        [0xF5, 0x1F],  # 3
        [0x47, 0x1F],  # 4
        [0xF7, 0x1D],  # 5
        [0xFF, 0x1D],  # 6
        [0x21, 0x1F],  # 7
        [0xFF, 0x1F],  # 8
        [0xF7, 0x1F],  # 9
        [0x44, 0x00],  # -
        [0x00, 0x00],  # white
        [0xFF, 0x00],  # E
        [0x5C, 0x00],  # r (big digits)
        [0x3F, 0x01],  # r (small digits)
    ]
    _NUM_MINUS = 10  # index int _NUMBERS
    _NUM_WHITE = 11  # index int _NUMBERS
    _OFFSET_TEMP = [1, 3, 11, 4]  # byte-offset for digits left to right, last
    _OFFSET_HUM = [5, 7, 9, 8]  # is byte for radix-point
    _POINT = 0x20
    DEG_C = 0x05
    DEG_F = 0x06
    _PER_CENT = 0x20
    _BELOW_10 = 0x04
    _ABOVE_99 = 0x1F
    _BT_ON = 0x08
    _POW_ON = 0x10

    # --- constructor   --------------------------------------------------------

    def __init__(self, i2c, rst_pin, busy_pin, temp=20):
        """constructor"""

        self._i2c = i2c
        self._temp = None
        self._buffer = bytearray(15)
        self._fullmode = False
        self._unit = SegmentDisplay.DEG_C

        self._busy_pin = digitalio.DigitalInOut(busy_pin)
        self._busy_pin.direction = digitalio.Direction.INPUT
        self._rst_pin = digitalio.DigitalInOut(rst_pin)
        self._rst_pin.direction = digitalio.Direction.OUTPUT
        self._rst_pin.value = False

    # --- initialize device   --------------------------------------------------

    def init(self, temp=None):
        """initialize device"""

        self.reset()
        time.sleep(0.1)

        self._send_command(0x2B)  # POWER_ON
        time.sleep(0.01)
        self._send_command(0xA7)  # boost
        self._send_command(0xE0)  # TSON
        time.sleep(0.01)
        self.update_mode(full=self._fullmode)

    # --- reset display   ------------------------------------------------------

    def reset(self):
        """reset display"""
        self._rst_pin.value = True
        time.sleep(0.2)
        self._rst_pin.value = False
        time.sleep(0.02)
        self._rst_pin.value = True
        time.sleep(0.2)

    # --- clean display   ------------------------------------------------------

    def clean(self):
        """clean display"""
        self._lut_GC()
        self.update(data=bytearray(b"\xff" * 15), black=True)
        time.sleep(1.0)
        self.update(data=bytearray(15))
        time.sleep(0.1)
        self.update_mode(full=self._fullmode)

    # --- clear display   ------------------------------------------------------

    def clear(self):
        """clear display"""
        self._lut_5S()
        self.update(data=bytearray(15))
        time.sleep(0.1)
        self.update_mode(full=self._fullmode)

    # --- set update-mode   ----------------------------------------------------

    def update_mode(self, full=False):
        """set update mode (full or partial)"""

        if full:
            self._lut_GC()
        else:
            self._lut_DU_WB()
        self._fullmode = full
        # time.sleep(0.5)

    # --- update display   -----------------------------------------------------

    def update(self, data=None, black=False):
        """update display with given or builtin buffer, enter sleep afterwards"""
        self._send_command(0xAC)  # Close the sleep
        self._send_command(0x2B)  # turn on the power
        self._send_command(0x40)  # Write RAM address
        self._send_command(0xA9)  # Turn on the first SRAM
        self._send_command(0xA8)  # Shut down the first SRAM

        for j in range(0, 15):
            if data is None:
                self._send_data(self._buffer[j])
            else:
                self._send_data(data[j])

        if black:
            self._send_data(0x03)  # Write_Screen1
        else:
            self._send_data(0x00)  # Write_Screen

        self._send_command(0xAB)  # Turn on the second SRAM
        self._send_command(0xAA)  # Shut down the second SRAM
        self._send_command(0xAF)  # display on
        self._wait_for_idle()
        self._send_command(0xAE)  # display off
        self._send_command(0x28)  # HV OFF
        self._send_command(0xAD)  # sleep in

    # --- put device into sleep-mode   -----------------------------------------

    def sleep(self):
        """enter sleep-mode"""
        self._send_command(0x28)  # POWER_OFF
        self._wait_for_idle()
        self._send_command(0xAD)  # DEEP_SLEEP

    # --- set value of temperature   -------------------------------------------

    def set_temperature(self, value, unit=None):
        """set value of temperature"""
        self._buffer[0] = 0
        if value > 199.9 or value < -99.9:
            self._set_error(SegmentDisplay._OFFSET_TEMP)
        else:
            self._adjust_temperature(value)
            self._set_digits(value, SegmentDisplay._OFFSET_TEMP)
        self.set_unit(unit if unit else self._unit)

    # --- set value of temperature   -------------------------------------------

    def set_humidity(self, value):
        """set value of humidity"""
        if value > 99.9 or value < 0:
            self._set_error(SegmentDisplay._OFFSET_HUM)
        else:
            self._set_digits(value, SegmentDisplay._OFFSET_HUM)
        self._buffer[10] |= SegmentDisplay._PER_CENT

    # --- set unit for degrees   -----------------------------------------------

    def set_unit(self, unit):
        """set unit for degrees"""

        self._buffer[13] &= ~self._unit  # clear old unit
        self._buffer[13] |= unit  # set new unit
        self._unit = unit

    # --- show bluetooth-sign   ------------------------------------------------

    def show_bluetooth(self, visible):
        """show bluetooth-symbol"""

        if visible:
            self._buffer[13] |= SegmentDisplay._BT_ON
        else:
            self._buffer[13] &= ~SegmentDisplay._BT_ON

    # --- show power-sign   ----------------------------------------------------

    def show_power(self, visible):
        """set unit for degrees"""

        if visible:
            self._buffer[13] |= SegmentDisplay._POW_ON
        else:
            self._buffer[13] &= ~SegmentDisplay._POW_ON

    # --- set digits   ---------------------------------------------------------

    def _set_digits(self, value, offsets):
        """set digits to given offsets in the buffer"""

        if value < 0:
            is_neg = True
            value *= -1
        else:
            is_neg = False
            if value > 99.9:
                self._buffer[0] = SegmentDisplay._ABOVE_99
                value -= 100

        # convert to integer with at most 3 digits
        # round away from zero at x.y5 (works, since value is positive)
        val = int(round(value * 10, 1) + 0.5)
        # split of digits from right
        (rest, d2) = divmod(val, 10)
        d2 = SegmentDisplay._NUMBERS[d2]
        if rest < 10:
            # e.g.: val = 5.2 -> 52 -> (5,2) with digits=[None,5,2]
            d1 = SegmentDisplay._NUMBERS[rest]
            d0 = (
                SegmentDisplay._NUMBERS[SegmentDisplay._NUM_MINUS]
                if is_neg
                else SegmentDisplay._NUMBERS[SegmentDisplay._NUM_WHITE]
            )
        else:
            # e.g.: val = 42.7 -> 427 -> (42,7) -> (4,2)+7  with digits=[4,2,7]
            (d0, d1) = divmod(rest, 10)
            d1 = SegmentDisplay._NUMBERS[d1]
            d0 = SegmentDisplay._NUMBERS[d0]
            if is_neg:
                # set leftmost minus
                self._buffer[0] = SegmentDisplay._BELOW_10

        # update buffer
        for i, d in enumerate([d0, d1, d2]):
            self._buffer[offsets[i] : offsets[i] + 2] = bytes(d)
        # add radix-point
        self._buffer[offsets[3]] |= SegmentDisplay._POINT

    # --- set error   ----------------------------------------------------------

    def _set_error(self, offsets):
        """set error to given offsets in the buffer"""

        for i, d in enumerate(SegmentDisplay._NUMBERS[-3:]):
            self._buffer[offsets[i] : offsets[i] + 2] = bytes(d)

    # --- send command to device   ---------------------------------------------

    def _send_command(self, value):
        """send a command to the device"""
        self._write_byte(SegmentDisplay._ADDR_COM, value)
        time.sleep(0.001)

    # --- send data to device   ------------------------------------------------

    def _send_data(self, value):
        """send data to the device"""
        self._write_byte(SegmentDisplay._ADDR_DATA, value)
        time.sleep(0.001)

    # --- wait for device   ----------------------------------------------------

    def _wait_for_idle(self):
        """wait for device to be ready"""
        while not self._busy_pin.value:  # busy is low
            time.sleep(0.001)
        time.sleep(0.01)

    # --- waveform DU_WB   -----------------------------------------------------

    def _lut_DU_WB(self):
        # DU waveform white extinction diagram + black out diagram
        # Bureau of brush waveform
        self._send_command(0x82)
        self._send_command(0x80)
        self._send_command(0x00)
        self._send_command(0xC0)
        self._send_command(0x80)
        self._send_command(0x80)
        self._send_command(0x62)

    # --- waveform DU_WB   -----------------------------------------------------

    def _lut_GC(self):
        # GC waveform
        # The brush waveform
        self._send_command(0x82)
        self._send_command(0x20)
        self._send_command(0x00)
        self._send_command(0xA0)
        self._send_command(0x80)
        self._send_command(0x40)
        self._send_command(0x63)

    # --- waveform DU_WB   -----------------------------------------------------

    def _lut_5S(self):
        # 5 waveform  better ghosting
        # Boot waveform
        self._send_command(0x82)
        self._send_command(0x28)
        self._send_command(0x20)
        self._send_command(0xA8)
        self._send_command(0xA0)
        self._send_command(0x50)
        self._send_command(0x65)

    # --- adjust configuration for temperature   -------------------------------

    def _adjust_temperature(self, temp):
        """adjust frame-time for temperature"""

        if self._temp is not None:
            # check if update is necessary
            if (
                self._temp < 5
                and temp < 5
                or self._temp < 10
                and temp < 10
                or self._temp < 15
                and temp < 15
                or self._temp < 20
                and temp < 20
                or self._temp >= 20
                and temp >= 20
            ):
                return
            else:
                self._temp = temp
        else:
            self._temp = temp

        if self._temp < 10:
            self._send_command(0x7E)
            self._send_command(0x81)
            self._send_command(0xB4)
        else:
            self._send_command(0x7B)
            self._send_command(0x81)
            self._send_command(0xB4)

        self._wait_for_idle()
        self._send_command(0xE7)  # Set default frame time

        # Set default frame time
        if self._temp < 5:
            self._send_command(0x31)  # 0x31  (49+1)*20ms=1000ms
        elif self._temp < 10:
            self._send_command(0x22)  # 0x22  (34+1)*20ms=700ms
        elif self._temp < 15:
            self._send_command(0x18)  # 0x18  (24+1)*20ms=500ms
        elif self._temp < 20:
            self._send_command(0x13)  # 0x13  (19+1)*20ms=400ms
        else:
            self._send_command(0x0E)  # 0x0e  (14+1)*20ms=300ms

    # --- low-level I2C-interface   --------------------------------------------

    def _write_byte(self, addr, value):
        """write a single byte to the given i2c-addr"""
        with I2CDevice(self._i2c, addr) as i2c:
            i2c.write(bytes([value]))
