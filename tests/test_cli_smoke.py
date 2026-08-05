# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2019 gfduszynski
"""Smoke tests for the click-based CLI entry points.

These only exercise --help / command registration, which click resolves
without invoking group callbacks, so no real CMRGBController (and therefore
no HID hardware) is ever touched. This is the class of bug that broke
cm-rgb-cli under Click 8.1+ (`resultcallback` was removed) -- these tests
would have caught it, since loading the module fails immediately if the
decorator doesn't exist.
"""

from unittest import mock

from click.testing import CliRunner


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

    def save(self):
        self.calls.append(("save",))


def test_cli_module_loads_and_registers_commands(load_script):
    cli = load_script("cm-rgb-cli")

    assert set(cli.main_group.commands) == {"restore", "version", "add-udev-rule", "set"}
    assert set(cli.setup_group.commands) == {"logo", "fan", "ring", "save"}


def test_cli_top_level_help(load_script):
    cli = load_script("cm-rgb-cli")

    result = CliRunner().invoke(cli.main_group, ["--help"])

    assert result.exit_code == 0
    assert "set" in result.output


def test_cli_set_help_lists_subcommands(load_script):
    cli = load_script("cm-rgb-cli")

    result = CliRunner().invoke(cli.main_group, ["set", "--help"])

    assert result.exit_code == 0
    for name in ("logo", "fan", "ring", "save"):
        assert name in result.output


def test_monitor_module_loads_and_help_works(load_script):
    monitor = load_script("cm-rgb-monitor")

    result = CliRunner().invoke(monitor.monitor, ["--help"])

    assert result.exit_code == 0
    assert "--mirage" in result.output


def test_cli_set_fan_chain_wires_through_to_controller(load_script):
    """End-to-end check of the chained `set ... save` pipeline, with a fake controller.

    This exercises the actual decorator wiring (in particular that every
    subcommand still receives its click context), not just --help text.
    """
    cli = load_script("cm-rgb-cli")
    fake_ctrl = FakeCtrl()

    with mock.patch.object(cli, "CMRGBController", return_value=fake_ctrl):
        result = CliRunner().invoke(cli.main_group, [
            "set", "fan", "--mode=static", "--color=#ff0000", "--mirage-red-freq=100", "save",
        ])

    assert result.exit_code == 0, result.output
    call_names = [call[0] for call in fake_ctrl.calls]
    assert call_names == ["set_channel", "enable_mirage", "assign_leds_to_channels", "apply", "save"]

    _, mirage_args = next(call for call in fake_ctrl.calls if call[0] == "enable_mirage")
    assert mirage_args == (100, 0, 0)
