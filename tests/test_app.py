import threading
import unittest
from unittest.mock import patch

from spatricius_monitor_toggle.app import MonitorIndicator
from spatricius_monitor_toggle.constants import ICON_BUSY, ICON_OFF


def make_output(name, enabled=True):
    return {
        "name": name,
        "enabled": enabled,
        "label": name,
        "short_label": name,
    }


def make_indicator(selected_outputs, auto_disable=False):
    with patch("spatricius_monitor_toggle.app.load_selected_outputs", return_value=list(selected_outputs)), \
         patch("spatricius_monitor_toggle.app.load_config", return_value=auto_disable):
        return MonitorIndicator()


class ResolveInitialSelectedOutputsTests(unittest.TestCase):
    def test_returns_saved_selection_unfiltered(self):
        # Regression: this used to call get_outputs() and silently swap in a
        # different connected monitor if the saved one wasn't present yet.
        with patch("spatricius_monitor_toggle.app.load_selected_outputs", return_value=["DP-1"]), \
             patch("spatricius_monitor_toggle.app.load_config", return_value=False), \
             patch("spatricius_monitor_toggle.app.get_outputs") as get_outputs:
            indicator = MonitorIndicator()
        get_outputs.assert_not_called()
        self.assertEqual(indicator.selected_outputs, ["DP-1"])


class RefreshStatusDisconnectTests(unittest.TestCase):
    def test_selection_survives_when_selected_monitor_is_unplugged(self):
        indicator = make_indicator(["DP-1"])
        with patch("spatricius_monitor_toggle.app.get_outputs",
                    return_value=[make_output("HDMI-1")]), \
             patch("spatricius_monitor_toggle.app.save_selected_outputs") as save:
            indicator.refresh_status(emit=False)

        self.assertEqual(indicator.selected_outputs, ["DP-1"])
        save.assert_not_called()

    def test_selection_not_emptied_either(self):
        indicator = make_indicator(["DP-1"])
        with patch("spatricius_monitor_toggle.app.get_outputs", return_value=[]):
            indicator.refresh_status(emit=False)

        self.assertEqual(indicator.selected_outputs, ["DP-1"])

    def test_enabled_state_is_false_while_selected_monitor_is_gone(self):
        indicator = make_indicator(["DP-1"])
        with patch("spatricius_monitor_toggle.app.get_outputs",
                    return_value=[make_output("HDMI-1", enabled=True)]):
            indicator.refresh_status(emit=False)

        self.assertFalse(indicator.enabled)

    def test_selection_resumes_working_once_monitor_reconnects(self):
        indicator = make_indicator(["DP-1"])
        with patch("spatricius_monitor_toggle.app.get_outputs",
                    return_value=[make_output("HDMI-1")]):
            indicator.refresh_status(emit=False)

        with patch("spatricius_monitor_toggle.app.get_outputs",
                    return_value=[make_output("DP-1", enabled=True)]):
            indicator.refresh_status(emit=False)

        self.assertEqual(indicator.selected_outputs, ["DP-1"])
        self.assertTrue(indicator.enabled)


class ManualSelectionStillPersistsTests(unittest.TestCase):
    def test_toggle_output_selection_still_saves_explicit_choice(self):
        indicator = make_indicator(["DP-1"])
        indicator.outputs = [make_output("DP-1"), make_output("HDMI-1")]

        with patch("spatricius_monitor_toggle.app.save_selected_outputs") as save:
            indicator.toggle_output_selection("HDMI-1")

        self.assertEqual(indicator.selected_outputs, ["DP-1", "HDMI-1"])
        save.assert_called_once_with(["DP-1", "HDMI-1"])

    def test_cannot_deselect_the_last_remaining_output(self):
        indicator = make_indicator(["DP-1"])
        indicator.outputs = [make_output("DP-1")]

        with patch("spatricius_monitor_toggle.app.save_selected_outputs") as save:
            indicator.toggle_output_selection("DP-1")

        self.assertEqual(indicator.selected_outputs, ["DP-1"])
        save.assert_not_called()


class StartupDelayTests(unittest.TestCase):
    """Layer 1 of the login-race fix (see project memory: a real display
    crash happened once from racing Mutter's own startup config restore).
    disable_on_startup() must be scheduled, never fired synchronously from
    on_bus_acquired - regressing this reopens that exact crash."""

    def test_on_bus_acquired_schedules_disable_instead_of_calling_it_directly(self):
        indicator = make_indicator(["DP-1"], auto_disable=True)
        with patch("spatricius_monitor_toggle.app.register_objects"), \
             patch("spatricius_monitor_toggle.app.watch_watcher"), \
             patch("spatricius_monitor_toggle.app.subscribe_changes"), \
             patch.object(MonitorIndicator, "refresh_status_async"), \
             patch.object(MonitorIndicator, "disable_on_startup") as disable_on_startup, \
             patch("spatricius_monitor_toggle.app.GLib.timeout_add_seconds") as timeout_add:
            indicator.on_bus_acquired(connection=object(), _name="test")

        disable_on_startup.assert_not_called()
        timeout_add.assert_called_once()
        delay_seconds, callback = timeout_add.call_args[0][:2]
        self.assertEqual(delay_seconds, 5)
        self.assertEqual(callback, indicator._delayed_disable_on_startup)


class StartupRefreshTests(unittest.TestCase):
    """The tray watcher reads our properties once, right after registration, and never
    retries. A display query holding the main loop at that moment leaves IconName empty,
    which Cinnamon renders as the broken-image placeholder for the whole session - so
    startup must not query the backend on the main thread."""

    def test_startup_queries_the_backend_off_the_main_thread(self):
        indicator = make_indicator(["DP-1"])
        queried_from = []
        done = threading.Event()

        def fake_get_outputs():
            queried_from.append(threading.current_thread())
            done.set()
            return [make_output("DP-1", enabled=False)]

        with patch("spatricius_monitor_toggle.app.register_objects"), \
             patch("spatricius_monitor_toggle.app.watch_watcher"), \
             patch("spatricius_monitor_toggle.app.subscribe_changes"), \
             patch("spatricius_monitor_toggle.app.get_outputs", side_effect=fake_get_outputs), \
             patch("spatricius_monitor_toggle.app.GLib.timeout_add_seconds"):
            indicator.on_bus_acquired(connection=object(), _name="test")
            self.assertTrue(done.wait(5))

        self.assertIsNot(queried_from[0], threading.current_thread())

    def test_refresh_status_async_queries_off_the_main_thread(self):
        indicator = make_indicator(["DP-1"])
        queried_from = []
        done = threading.Event()

        def fake_get_outputs():
            queried_from.append(threading.current_thread())
            done.set()
            return [make_output("DP-1", enabled=False)]

        with patch("spatricius_monitor_toggle.app.get_outputs", side_effect=fake_get_outputs), \
             patch("spatricius_monitor_toggle.app.GLib.idle_add"):
            indicator.refresh_status_async()
            self.assertTrue(done.wait(5))
            indicator.refresh_status_async()

        self.assertIsNot(queried_from[0], threading.current_thread())
        self.assertEqual(len(queried_from), 1)

    def test_apply_status_uses_the_query_result(self):
        indicator = make_indicator(["DP-1"])
        indicator.refreshing = True

        indicator._apply_status([make_output("DP-1", enabled=False)], False, None)

        self.assertFalse(indicator.refreshing)
        self.assertEqual(indicator.icon_file, ICON_OFF)

    def test_apply_status_marks_status_unavailable_on_error(self):
        indicator = make_indicator(["DP-1"])
        indicator.refreshing = True

        indicator._apply_status(None, None, RuntimeError("no backend"))

        self.assertFalse(indicator.refreshing)
        self.assertEqual(indicator.icon_file, ICON_BUSY)


class DisableOnStartupTests(unittest.TestCase):
    def test_does_nothing_when_auto_disable_is_off(self):
        indicator = make_indicator(["DP-1"], auto_disable=False)

        with patch("spatricius_monitor_toggle.app.auto_disable_startup") as backend_call:
            indicator.disable_on_startup()

        backend_call.assert_not_called()

    def test_passes_the_persisted_selection_through_unfiltered(self):
        # app.py no longer checks whether the selected monitor is actually
        # connected before calling this - that responsibility now lives
        # entirely in the backend (see test_mutter_display_config.py).
        indicator = make_indicator(["DP-1"], auto_disable=True)

        with patch("spatricius_monitor_toggle.app.auto_disable_startup") as backend_call, \
             patch.object(MonitorIndicator, "run_in_background", lambda self, action: action()):
            indicator.disable_on_startup()

        backend_call.assert_called_once_with(["DP-1"])


if __name__ == "__main__":
    unittest.main()
