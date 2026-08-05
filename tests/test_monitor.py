# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2019 gfduszynski
"""Unit tests for the pure-logic helpers in scripts/cm-rgb-monitor."""

from unittest import mock

import pytest
from click.testing import CliRunner


@pytest.fixture
def monitor(load_script):
    return load_script("cm-rgb-monitor")


class FakeCtrl:
    """Stand-in for CMRGBController that records calls instead of touching hardware."""

    def __init__(self):
        self.calls = []

    def set_channel(self, *args, **kwargs):
        self.calls.append(("set_channel", args, kwargs))

    def enable_mirage(self, *args):
        self.calls.append(("enable_mirage", args))

    def assign_leds_to_channels(self, *args):
        self.calls.append(("assign_leds_to_channels", args))

    def apply(self):
        self.calls.append(("apply",))

    def restore(self):
        self.calls.append(("restore",))


def test_monitor_end_to_end_with_sensors_and_mirage(monitor):
    """Run a couple of real loop iterations through the click command with everything mocked.

    This exercises the full wiring (option parsing -> MonitorConfig -> run_monitor
    -> per-iteration helpers), not just the individual helper functions in isolation.
    """
    fake_ctrl = FakeCtrl()
    fake_temps = {"k10temp": [mock.Mock(label="Tdie", current=55.0)]}
    fake_fans = {"nct6797": [mock.Mock(current=1200.0)]}

    iteration_count = {"n": 0}

    def fake_sleep(_interval):
        iteration_count["n"] += 1
        if iteration_count["n"] >= 2:
            raise SystemExit

    with mock.patch.object(monitor, "CMRGBController", return_value=fake_ctrl), \
            mock.patch.object(monitor.psutil, "sensors_temperatures", return_value=fake_temps), \
            mock.patch.object(monitor.psutil, "sensors_fans", return_value=fake_fans), \
            mock.patch.object(monitor.psutil, "cpu_percent", return_value=42), \
            mock.patch.object(monitor.psutil, "cpu_freq",
                               side_effect=lambda percpu=False: (
                                   [mock.Mock(current=3000)] if percpu
                                   else mock.Mock(current=3000, min=800, max=4000))), \
            mock.patch.object(monitor.atexit, "register"), \
            mock.patch.object(monitor.time, "sleep", side_effect=fake_sleep):
        result = CliRunner().invoke(monitor.monitor, [
            "--show-temp", "--temp-source=k10temp/Tdie",
            "--show-cpu-frequency",
            "--mirage", "--mirage-fan=nct6797/0",
            "--interval=0",
        ])

    assert iteration_count["n"] >= 2
    call_names = [call[0] for call in fake_ctrl.calls]
    # init_channels: 2x set_channel + apply, then per loop iteration:
    # temperature + frequency set_channel, enable_mirage, assign_leds_to_channels, apply.
    assert call_names[:3] == ["set_channel", "set_channel", "apply"]
    assert call_names[3:8] == ["set_channel", "set_channel", "enable_mirage",
                                "assign_leds_to_channels", "apply"]


def test_interpolate_color_extremes_and_midpoint(monitor):
    low = [0, 0, 0]
    high = [200, 100, 50]

    assert monitor.interpolate_color(low, high, 0) == [0, 0, 0]
    assert monitor.interpolate_color(low, high, 1) == [200, 100, 50]
    assert monitor.interpolate_color(low, high, 0.5) == [100, 50, 25]


def test_parse_mirage_factors_three_values(monitor):
    assert monitor.parse_mirage_factors("1.0,2.0,3.0") == [1.0, 2.0, 3.0]


def test_parse_mirage_factors_single_value_broadcasts(monitor):
    assert monitor.parse_mirage_factors("7.5") == [7.5, 7.5, 7.5]


def test_ring_leds_for_cpu_load_rotates_arc_by_8(monitor):
    # 33% load -> round(15 * 0.333) = 5 "cpu" LEDs followed by 10 "bg" LEDs,
    # then rotated so index 0 of the returned list corresponds to physical
    # ring position 8.
    leds = monitor.ring_leds_for_cpu_load(bg_channel="BG", cpu_channel="CPU", cpu_percent=33.3)

    assert len(leds) == 15
    unrotated = leds[-8:] + leds[:-8]
    assert unrotated == ["CPU"] * 5 + ["BG"] * 10


def test_ring_leds_for_cpu_load_zero_percent_is_all_background(monitor):
    leds = monitor.ring_leds_for_cpu_load(bg_channel="BG", cpu_channel="CPU", cpu_percent=0)

    assert leds == ["BG"] * 15


def test_ring_leds_for_cpu_load_full_percent_is_all_cpu(monitor):
    leds = monitor.ring_leds_for_cpu_load(bg_channel="BG", cpu_channel="CPU", cpu_percent=100)

    assert leds == ["CPU"] * 15


def test_resolve_temp_sensor_finds_matching_label(monitor):
    fake_sensor = mock.Mock(label="Tdie")
    fake_temps = {"k10temp": [mock.Mock(label="Tctl"), fake_sensor]}

    with mock.patch.object(monitor.psutil, "sensors_temperatures", return_value=fake_temps):
        group, label, index = monitor.resolve_temp_sensor("k10temp/Tdie")

    assert (group, label, index) == ("k10temp", "Tdie", 1)


def test_resolve_temp_sensor_raises_when_label_not_found(monitor):
    fake_temps = {"k10temp": [mock.Mock(label="Tctl")]}

    with mock.patch.object(monitor.psutil, "sensors_temperatures", return_value=fake_temps):
        with pytest.raises(KeyError):
            monitor.resolve_temp_sensor("k10temp/Tdie")


def test_init_channels_sets_background_and_cpu_channels(monitor):
    ctrl = mock.Mock()
    config = monitor.MonitorConfig(
        bg_color=[0, 255, 255], cpu_color=[255, 165, 0], brightness=0xCC, interval=0.2,
        verbose=False, show_sensor=False, temp_source="", temp_low=50, temp_high=80,
        temp_low_color=[0, 0, 0], temp_high_color=[0, 0, 0], show_cpu_freq=False,
        freq_low_color=[0, 0, 0], freq_high_color=[0, 0, 0], smoothing=0.8,
        mirage=False, mirage_fan="", mirage_factors=None,
    )

    bg_channel, cpu_channel = monitor.init_channels(ctrl, config)

    assert bg_channel is monitor.LedChannel.R_STATIC
    assert cpu_channel is monitor.LedChannel.R_SWIRL
    ctrl.set_channel.assert_any_call(bg_channel, monitor.LedMode.R_DEFAULT, 0xCC, 0, 255, 255)
    ctrl.set_channel.assert_any_call(cpu_channel, monitor.LedMode.R_DEFAULT, 0xCC, 255, 165, 0, 0x60)
    ctrl.apply.assert_called_once()
