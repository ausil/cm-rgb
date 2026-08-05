# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2019 gfduszynski
"""Unit tests for cm_rgb.ctrl.CMRGBController's packet-building logic.

These tests never touch real hardware: CMRGBController.__init__() opens a USB
HID device, so instances are built with object.__new__() and given a
FakeDevice that just records what would have been written.
"""

from cm_rgb.ctrl import CMRGBController, LedChannel, LedMode, hex_to_rgb


def test_hex_to_rgb_parses_with_and_without_hash():
    assert hex_to_rgb("#FFA500") == [0xFF, 0xA5, 0x00]
    assert hex_to_rgb("00ffcc") == [0x00, 0xFF, 0xCC]


class FakeDevice:
    """Stand-in for hid.device() that records writes and returns a fixed reply."""

    def __init__(self, reply=None):
        self.written = []
        self._reply = reply if reply is not None else bytearray(64)

    def write(self, packet):
        self.written.append(bytearray(packet))
        return len(packet)

    def read(self, _size):
        return self._reply


def make_controller(reply=None):
    """Build a CMRGBController without opening a real USB device."""
    ctrl = object.__new__(CMRGBController)
    ctrl.device = FakeDevice(reply)
    return ctrl


def test_new_packet_sets_report_id_and_places_args():
    pkt = CMRGBController.new_packet(0xAB, 1, 2, 3)

    assert len(pkt) == 65
    assert pkt[0] == 0
    assert list(pkt[1:4]) == [1, 2, 3]
    assert all(b == 0xAB for b in pkt[4:])


def test_new_packet_no_args_fills_completely_except_report_id():
    pkt = CMRGBController.new_packet(0x11)

    assert pkt[0] == 0
    assert all(b == 0x11 for b in pkt[1:])


def test_set_channel_packet_layout():
    ctrl = make_controller()

    ctrl.set_channel(LedChannel.LOGO, LedMode.STATIC, 0xFF, 0x10, 0x20, 0x30, speed=0x3C, color_source=0x20)

    pkt = ctrl.device.written[-1]
    assert (pkt[1], pkt[2]) == (0x51, 0x2C)
    assert pkt[5] == LedChannel.LOGO.value
    assert pkt[6] == 0x3C
    assert pkt[7] == 0x20
    assert pkt[8] == LedMode.STATIC.value
    assert pkt[10] == 0xFF
    assert list(pkt[11:14]) == [0x10, 0x20, 0x30]


def test_assign_leds_to_channels_maps_logo_fan_and_ring():
    ctrl = make_controller()
    ring = [LedChannel.R_STATIC] * 5

    ctrl.assign_leds_to_channels(LedChannel.LOGO, LedChannel.FAN, *ring)

    pkt = ctrl.device.written[-1]
    assert pkt[9] == LedChannel.LOGO.value
    assert pkt[10] == LedChannel.FAN.value
    assert list(pkt[11:16]) == [LedChannel.R_STATIC.value] * 5
    assert list(pkt[16:26]) == [LedChannel.OFF.value] * 10


def test_assign_leds_to_channels_ignores_ring_args_past_15_slots():
    ctrl = make_controller()
    ring = [LedChannel.R_RAINBOW] * 20

    ctrl.assign_leds_to_channels(LedChannel.LOGO, LedChannel.FAN, *ring)

    pkt = ctrl.device.written[-1]
    assert list(pkt[11:26]) == [LedChannel.R_RAINBOW.value] * 15


def test_enable_mirage_zero_hz_writes_off_marker_for_each_channel():
    ctrl = make_controller()

    ctrl.enable_mirage(0, 0, 0)

    pkt = ctrl.device.written[-1]
    assert list(pkt[9:13]) == [0x02, 0x00, 0xFF, 0x4A]
    assert list(pkt[13:17]) == [0x03, 0x00, 0xFF, 0x4A]
    assert list(pkt[17:21]) == [0x04, 0x00, 0xFF, 0x4A]


def test_disable_mirage_delegates_to_enable_mirage_zero():
    ctrl = make_controller()

    ctrl.disable_mirage()

    # enable_mirage() already writes its own packet and returns the device's
    # *reply*, not the packet bytes -- disable_mirage() must not wrap that
    # reply in a second send_packet() call, or it re-sends garbage.
    assert len(ctrl.device.written) == 1
    pkt = ctrl.device.written[-1]
    assert list(pkt[9:13]) == [0x02, 0x00, 0xFF, 0x4A]


def test_restore_only_sends_one_mirage_off_packet():
    ctrl = make_controller()

    ctrl.restore()

    mirage_packets = [pkt for pkt in ctrl.device.written if pkt[1] == 0x51 and pkt[2] == 0x71]
    assert len(mirage_packets) == 1
    assert list(mirage_packets[0][9:13]) == [0x02, 0x00, 0xFF, 0x4A]


def test_get_version_reads_every_second_byte_starting_at_offset_8():
    reply = bytearray(64)
    version = "1.2.3.45"
    for idx, ch in enumerate(version):
        reply[8 + idx * 2] = ord(ch)

    ctrl = make_controller(reply=reply)

    assert ctrl.get_version() == version + "\x00" * 8


def test_get_version_stops_at_first_zero_byte():
    reply = bytearray(64)
    reply[8] = ord("1")
    reply[10] = ord(".")
    # reply[12] is left at 0, so parsing stops there even though reply[14] is set
    reply[14] = ord("9")

    ctrl = make_controller(reply=reply)

    assert ctrl.get_version() == "1." + "\x00" * 14
