# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2019 gfduszynski
"""Low level protocol driver for the AMD Wraith Prism / CM RGB USB HID controller."""

import math
from enum import Enum

import hid


def hex_to_rgb(color):
    """Convert a "#RRGGBB" (or "RRGGBB") string into an [r, g, b] byte list."""
    color = color.lstrip('#')
    return [int(color[i:i + 2], 16) for i in (0, 2, 4)]


class LedChannel(Enum):
    """Physical/virtual LED channel identifiers used when assigning LEDs to effects."""

    R_STATIC = 0x00
    R_BREATHE = 0x01
    R_CYCLE = 0x02
    LOGO = 0x05
    FAN = 0x06
    R_RAINBOW = 0x07
    R_SWIRL = 0x0A
    OFF = 0xFE


class LedMode(Enum):
    """Effect mode byte used when configuring a channel."""

    OFF = 0x00
    STATIC = 0x01
    CYCLE = 0x02
    BREATHE = 0x03
    R_RAINBOW = 0x05
    R_SWIRL = 0x4a
    R_DEFAULT = 0xFF


class CMRGBController:
    """Talks to the CM RGB USB HID device to configure and apply LED effects."""

    VENDOR_ID = 0x2516
    PRODUCT_ID = 0x0051
    PRODUCT_STR = 'CYRM02p0303h00E0r0100'
    IFACE_NUM = 1

    @staticmethod
    def new_packet(fill, *args):
        """Build a 65 byte HID packet: report ID 0, then args, padded with fill."""
        pkt = bytearray([fill] * 65)
        pkt[0] = 0  # Report ID
        for i, v in enumerate(args):
            pkt[i + 1] = v
        return pkt

    # 52 get / 51 SET - looks like even numbers are getters and odd setters
    P_POWER_ON = new_packet.__func__(0, 0x41, 0x80)
    P_POWER_OFF = new_packet.__func__(0, 0x41, 0x03)
    P_RESTORE = new_packet.__func__(0, 0x41)
    P_LED_LOAD = new_packet.__func__(0, 0x50)
    P_LED_SAVE = new_packet.__func__(0, 0x50, 0x55)
    P_APPLY = new_packet.__func__(0, 0x51, 0x28, 0x00, 0x00, 0xe0)
    P_MAGIC_2 = new_packet.__func__(0, 0x51, 0x96)
    P_MIRAGE_OFF = new_packet.__func__(
        0, 0x51, 0x71, 0x00, 0x00, 0x01, 0x00, 0xFF, 0x4A, 0x02, 0x00, 0xFF, 0x4A, 0x03,
        0x00, 0xFF, 0x4A, 0x04, 0x00, 0xFF, 0x4A)
    P_GET_VER = new_packet.__func__(0, 0x12, 0x20)

    def __init__(self):
        self.device = None
        self.__init_hid_device()
        self.__init_controller()

    def __init_hid_device(self):
        device_list = [x for x in hid.enumerate(self.VENDOR_ID, self.PRODUCT_ID)
                       if x['interface_number'] == self.IFACE_NUM]
        if len(device_list) == 0:
            raise RuntimeError(
                "No devices found. See: https://github.com/gfduszynski/cm-rgb/issues/9")

        self.device = hid.device()

        try:
            self.device.open_path(device_list[0]["path"])
        except OSError:
            print("Failed to access usb device. See: https://github.com/gfduszynski/cm-rgb/wiki/"
                  "1.-Installation-&-Configuration#3-configuration")
            print("Also check if other process is not using the device.\n")
            raise

    def __init_controller(self):
        # Without this controller wont accept changes
        self.send_packet(self.P_POWER_ON)

        # No idea what this does but it's in original startup sequence
        self.send_packet(self.P_MAGIC_2)

        # Some sort of apply / flush op
        self.apply()

    def send_packet(self, packet):
        """Write a packet to the device and return its reply."""
        self.device.write(packet)
        return self.device.read(64)

    def apply(self):
        """Flush pending channel/mirage configuration to the device."""
        return self.send_packet(self.P_APPLY)

    def save(self):
        """Persist the currently applied configuration to the device's onboard memory."""
        return self.send_packet(self.P_LED_SAVE)

    def restore(self):
        """Reset the device back to its onboard-saved configuration."""
        self.enable_mirage(0, 0, 0)
        self.send_packet(self.P_LED_LOAD)
        self.send_packet(self.P_POWER_OFF)
        self.send_packet(self.P_RESTORE)
        self.apply()

    def disable_mirage(self):
        """Turn off the mirage (fan-speed strobe) effect."""
        self.enable_mirage(0, 0, 0)

    def enable_mirage(self, r_hz, g_hz, b_hz):
        """Enable the mirage effect, strobing each color channel at its own frequency."""
        def hz_to_bytes(hz):
            if hz == 0:
                return [0x00, 0xFF, 0x4A]
            v = 187498.0 / hz
            v_mul = math.floor(v / 256.0)
            v_rem = v / (v_mul + 1)
            return [min(v_mul, 255), math.floor(v_rem % 1 * 256), math.floor(v_rem)]

        r_bytes = hz_to_bytes(r_hz)
        g_bytes = hz_to_bytes(g_hz)
        b_bytes = hz_to_bytes(b_hz)

        pkt = self.new_packet(
            0, 0x51, 0x71, 0x00, 0x00,
            # This part is probably for white LED's that did not find their way into final cooler
            0x01, 0x00, 0xFF, 0x4A,
            0x02, r_bytes[0], r_bytes[1], r_bytes[2],
            0x03, g_bytes[0], g_bytes[1], g_bytes[2],
            0x04, b_bytes[0], b_bytes[1], b_bytes[2])
        return self.send_packet(pkt)

    def get_version(self):
        """Read the firmware version string reported by the device."""
        reply = self.send_packet(self.P_GET_VER)
        fv = bytearray(16)

        i = 0
        while i < 16:
            if reply[i + 0x08] != 0:
                fv[int(i / 2)] = fv[int(i / 2)] + reply[i + 0x08]
            else:
                break
            i += 2

        return fv.decode("utf-8")

    # color_source 0x20 takes supplied color for breathe mode
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def set_channel(self, channel, mode, brightness, r, g, b, speed=0xff, color_source=0x20):
        """Configure one LED channel's mode, brightness, color and effect speed."""
        pkt = self.new_packet(0xff, 0x51, 0x2C, 0x01, 0x0, channel.value, speed, color_source,
                               mode.value, 0xFF, brightness, r, g, b, 0x00, 0x00, 0x00)
        return self.send_packet(pkt)

    def assign_leds_to_channels(self, logo, fan, *ring):
        """Map the logo, fan and up to 15 ring LEDs to previously configured channels."""
        pkt = self.new_packet(0x00, 0x51, 0xA0, 0x01, 0, 0, 0x03, 0, 0, logo.value, fan.value)
        j = 0
        # Ring LED's
        for i in range(11, 26):
            if j < len(ring):
                pkt[i] = ring[j].value
                j += 1
            else:
                pkt[i] = LedChannel.OFF.value

        return self.send_packet(pkt)
