import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib

from spatricius_monitor_toggle import mutter_display_config as mdc


def mode(mode_id="mode1", width=1920, height=1080, current=True, preferred=True):
    return (mode_id, width, height, 60.0, 1.0, [1.0],
            {"is-current": current, "is-preferred": preferred})


class ToggleOutputsMissingSelectionTests(unittest.TestCase):
    """The backend is the actual safety net for the "selection jumps to
    another monitor on unplug" bug: app.py no longer filters the saved
    selection, so it's this no-op-on-missing-output behavior that must hold.
    """

    def test_missing_selected_output_notifies_and_never_touches_dbus(self):
        monitors = [(("HDMI-1", "V", "P", "S"), [], {})]
        with patch.object(mdc, "_get_current_state", return_value=(1, monitors, [], {})), \
             patch.object(mdc, "notify") as notify, \
             patch.object(mdc, "_call") as call:
            mdc.toggle_outputs(["DP-1"])

        notify.assert_called_once()
        self.assertIn("Could not find output(s)", notify.call_args[0][0])
        call.assert_not_called()


class AutoDisableStartupTests(unittest.TestCase):
    def test_does_nothing_when_selected_monitor_is_disconnected(self):
        outputs = [{"name": "HDMI-1", "enabled": True, "label": "HDMI-1", "short_label": "HDMI-1"}]
        with patch.object(mdc, "_wait_for_stable_state"), \
             patch.object(mdc, "get_outputs", return_value=outputs), \
             patch.object(mdc, "toggle_outputs") as toggle:
            mdc.auto_disable_startup(["DP-1"])

        toggle.assert_not_called()

    def test_disables_the_selected_monitor_when_present_and_enabled(self):
        outputs = [{"name": "DP-1", "enabled": True, "label": "DP-1", "short_label": "DP-1"}]
        with patch.object(mdc, "_wait_for_stable_state"), \
             patch.object(mdc, "get_outputs", return_value=outputs), \
             patch.object(mdc, "toggle_outputs") as toggle:
            mdc.auto_disable_startup(["DP-1"])

        toggle.assert_called_once_with(["DP-1"], mdc.MUTTER_LAYOUT_FILE)

    def test_does_nothing_when_selected_monitor_already_disabled(self):
        outputs = [{"name": "DP-1", "enabled": False, "label": "DP-1", "short_label": "DP-1"}]
        with patch.object(mdc, "_wait_for_stable_state"), \
             patch.object(mdc, "get_outputs", return_value=outputs), \
             patch.object(mdc, "toggle_outputs") as toggle:
            mdc.auto_disable_startup(["DP-1"])

        toggle.assert_not_called()


class NeverBlankEveryScreenTests(unittest.TestCase):
    """The one guard that stands directly between this app and a fully
    black desktop. See project memory: a real crash happened here once
    (a login-timing race, not a logic bug in this guard) - these tests
    lock down the guard itself so it can't silently regress."""

    def test_refuses_when_the_only_enabled_monitor_is_selected(self):
        monitors = [(("DP-1", "V", "P", "S"), [mode()], {})]
        logical_monitors = [(0, 0, 1, 0, True, [("DP-1", "mode1", {})], {})]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mdc, "_get_current_state", return_value=(1, monitors, logical_monitors, {})), \
             patch.object(mdc, "notify") as notify, \
             patch.object(mdc, "_commit") as commit:
            mdc.toggle_outputs(["DP-1"], layout_file=Path(tmp) / "layout.json")

        commit.assert_not_called()
        notify.assert_called_once()
        self.assertIn("Refusing to disable every active screen", notify.call_args[0][0])

    def test_refuses_when_every_currently_enabled_monitor_is_selected(self):
        monitors = [
            (("DP-1", "V", "P", "S"), [mode()], {}),
            (("HDMI-1", "V", "P", "S"), [mode()], {}),
        ]
        logical_monitors = [
            (0, 0, 1, 0, True, [("DP-1", "mode1", {})], {}),
            (1920, 0, 1, 0, False, [("HDMI-1", "mode1", {})], {}),
        ]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mdc, "_get_current_state", return_value=(1, monitors, logical_monitors, {})), \
             patch.object(mdc, "notify") as notify, \
             patch.object(mdc, "_commit") as commit:
            mdc.toggle_outputs(["DP-1", "HDMI-1"], layout_file=Path(tmp) / "layout.json")

        commit.assert_not_called()
        notify.assert_called_once()
        self.assertIn("Refusing to disable every active screen", notify.call_args[0][0])

    def test_allows_disabling_a_subset_leaving_one_monitor_enabled(self):
        # Sanity check for the guard above: it must not be so broad that it
        # blocks a legitimate partial disable.
        monitors = [
            (("DP-1", "V", "P", "S"), [mode()], {}),
            (("HDMI-1", "V", "P", "S"), [mode()], {}),
        ]
        logical_monitors = [
            (0, 0, 1, 0, True, [("DP-1", "mode1", {})], {}),
            (1920, 0, 1, 0, False, [("HDMI-1", "mode1", {})], {}),
        ]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mdc, "_get_current_state", return_value=(1, monitors, logical_monitors, {})), \
             patch.object(mdc, "notify") as notify, \
             patch.object(mdc, "_commit") as commit:
            mdc.toggle_outputs(["HDMI-1"], layout_file=Path(tmp) / "layout.json")

        commit.assert_called_once()
        notify.assert_not_called()

    def test_final_hard_stop_refuses_even_if_the_earlier_count_check_would_allow_it(self):
        """Defense in depth: the code re-derives "what survives" independently
        right before committing, and refuses if that comes out empty - even
        when the earlier enabled-count arithmetic thought something would
        remain. Simulated here by making _enabled_geometry claim an extra
        enabled monitor that doesn't actually appear in logical_monitors,
        so the two computations disagree the way a real edge case might."""
        monitors = [
            (("DP-1", "V", "P", "S"), [mode()], {}),
            (("PHANTOM", "V", "P", "S"), [mode()], {}),
        ]
        logical_monitors = [(0, 0, 1, 0, True, [("DP-1", "mode1", {})], {})]
        fake_geometry = {
            "DP-1": (0, 0, 1, 0, True),
            "PHANTOM": (1920, 0, 1, 0, False),
        }

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mdc, "_get_current_state", return_value=(1, monitors, logical_monitors, {})), \
             patch.object(mdc, "_enabled_geometry", return_value=fake_geometry), \
             patch.object(mdc, "notify") as notify, \
             patch.object(mdc, "_commit") as commit:
            mdc.toggle_outputs(["DP-1"], layout_file=Path(tmp) / "layout.json")

        commit.assert_not_called()
        notify.assert_called_once()
        self.assertIn("Refusing to disable every active screen", notify.call_args[0][0])


class WaitForStableStateTests(unittest.TestCase):
    """Layer 2 of the login-race fix: startup must not act until Mutter's
    own config serial has genuinely stopped changing, not just been read
    once. Must also be bounded, or a permanently-erroring D-Bus call would
    hang startup forever instead of just skipping the auto-disable."""

    def test_does_not_return_on_the_very_first_read(self):
        with patch.object(mdc, "_get_current_state", return_value=(1, None, None, None)), \
             patch.object(mdc.time, "sleep") as sleep:
            mdc._wait_for_stable_state(tries=1, interval=0.01)

        sleep.assert_called_once()

    def test_returns_as_soon_as_two_consecutive_reads_match(self):
        with patch.object(mdc, "_get_current_state",
                           side_effect=[(1, None, None, None), (1, None, None, None)]), \
             patch.object(mdc.time, "sleep") as sleep:
            mdc._wait_for_stable_state(tries=10, interval=0.01)

        sleep.assert_called_once()

    def test_gives_up_after_tries_when_state_never_stabilizes(self):
        with patch.object(mdc, "_get_current_state",
                           side_effect=GLib.Error("boom")), \
             patch.object(mdc.time, "sleep") as sleep:
            mdc._wait_for_stable_state(tries=4, interval=0.01)

        self.assertEqual(sleep.call_count, 4)


class LayoutGeometrySafetyTests(unittest.TestCase):
    """Mutter rejects layouts whose origin isn't (0, 0) or that don't have
    exactly one primary monitor - these two helpers must always produce a
    layout Mutter will actually accept, or the apply silently fails."""

    def test_normalize_origin_shifts_everything_to_zero(self):
        layout = [{"x": 100, "y": 50}, {"x": 300, "y": 50}]
        mdc._normalize_origin(layout)
        self.assertEqual(min(lm["x"] for lm in layout), 0)
        self.assertEqual(min(lm["y"] for lm in layout), 0)

    def test_normalize_origin_handles_empty_layout(self):
        mdc._normalize_origin([])  # must not raise

    def test_ensure_primary_picks_one_when_none_is_marked(self):
        layout = [{"primary": False}, {"primary": False}]
        mdc._ensure_primary(layout)
        self.assertEqual(sum(1 for lm in layout if lm["primary"]), 1)

    def test_ensure_primary_resolves_conflicting_primaries(self):
        layout = [{"primary": True}, {"primary": True}]
        mdc._ensure_primary(layout)
        self.assertEqual(sum(1 for lm in layout if lm["primary"]), 1)

    def test_ensure_primary_handles_empty_layout(self):
        mdc._ensure_primary([])  # must not raise


if __name__ == "__main__":
    unittest.main()
