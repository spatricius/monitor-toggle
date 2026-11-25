import threading
import unittest
from unittest import mock
from unittest.mock import patch

from spatricius_monitor_toggle.app import MonitorIndicator, ICON_PULSE_DELAYS_MS
from spatricius_monitor_toggle.constants import ICON_BUSY, ICON_OFF, ICON_ON


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

        with patch("spatricius_monitor_toggle.app.save_selected_outputs") as save, \
             patch.object(MonitorIndicator, "refresh_status_async"):
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


class IconPulseTests(unittest.TestCase):
    """Why this exists: xapp-sn-watcher exports an XAppStatusIcon whose icon name
    is libxapp's placeholder (" ") and only fills in real values one round trip
    later. Cinnamon's StatusNotifier proxy is created in that window and keeps the
    placeholder, and libxapp only emits PropertiesChanged when a value actually
    changes - so nothing ever corrects it and St draws "image-missing" (white
    page, grey warning triangle) for the whole session. One real icon-name change
    after registration is what unsticks the tray icon."""

    def test_registering_with_the_watcher_schedules_the_transitions(self):
        indicator = make_indicator(["DP-1"])

        with patch("spatricius_monitor_toggle.app.register_with_watcher"), \
             patch.object(MonitorIndicator, "_schedule_icon_pulses") as schedule:
            indicator._register_with_watcher(connection=object())

        schedule.assert_called_once()

    def test_transitions_are_scheduled_more_than_once(self):
        indicator = make_indicator(["DP-1"])

        with patch("spatricius_monitor_toggle.app.GLib.timeout_add") as timeout_add:
            indicator._schedule_icon_pulses()

        delays = [call.args[0] for call in timeout_add.call_args_list]
        self.assertEqual(delays, list(ICON_PULSE_DELAYS_MS))

    def test_pulse_switches_to_busy_and_schedules_a_real_refresh(self):
        indicator = make_indicator(["DP-1"])
        indicator.connection = object()
        indicator.outputs = [make_output("DP-1", enabled=True)]
        indicator.enabled = True
        indicator.icon_file = ICON_ON

        with patch.object(MonitorIndicator, "emit_changes"), \
             patch.object(MonitorIndicator, "refresh_status_async") as refresh, \
             patch("spatricius_monitor_toggle.app.GLib.timeout_add") as timeout_add:
            indicator._pulse_icon()

            self.assertEqual(indicator.icon_file, ICON_BUSY)
            timeout_add.assert_called_once()
            _delay_ms, callback = timeout_add.call_args[0][:2]
            self.assertEqual(callback, indicator._end_icon_pulse)

            callback()

        refresh.assert_called_once()

    def test_finished_pulse_does_not_clobber_a_running_toggle(self):
        indicator = make_indicator(["DP-1"])
        indicator.busy = True

        with patch.object(MonitorIndicator, "refresh_status_async") as refresh:
            indicator._end_icon_pulse()

        refresh.assert_not_called()

    def test_pulse_is_skipped_while_a_toggle_is_running(self):
        indicator = make_indicator(["DP-1"])
        indicator.connection = object()
        indicator.busy = True

        with patch.object(MonitorIndicator, "emit_changes"), \
             patch("spatricius_monitor_toggle.app.GLib.timeout_add") as timeout_add:
            indicator._pulse_icon()

        timeout_add.assert_not_called()


class HandlersStayOffTheMainThreadTests(unittest.TestCase):
    """A blocking display query on the main loop makes the tray watcher's
    Get/GetAll time out (5s) and it never retries, leaving the placeholder icon
    name in place - so no D-Bus/menu handler may use the synchronous query."""

    def test_context_menu_does_not_query_the_backend_synchronously(self):
        indicator = make_indicator(["DP-1"])

        with patch.object(MonitorIndicator, "refresh_status") as sync_refresh, \
             patch.object(MonitorIndicator, "refresh_status_async") as async_refresh:
            indicator.on_item_method_call(
                None, None, None, None, "ContextMenu", None, mock.Mock()
            )

        sync_refresh.assert_not_called()
        async_refresh.assert_called_once()

    def test_menu_about_to_show_does_not_query_the_backend_synchronously(self):
        indicator = make_indicator(["DP-1"])

        with patch.object(MonitorIndicator, "refresh_status") as sync_refresh, \
             patch.object(MonitorIndicator, "refresh_status_async") as async_refresh:
            indicator.on_menu_method_call(
                None, None, None, None, "AboutToShow", mock.Mock(), mock.Mock()
            )

        sync_refresh.assert_not_called()
        async_refresh.assert_called_once()


class ItemPropertyGetterTests(unittest.TestCase):
    """The host reads every property through one GetAll. Rendering the SVG for
    IconPixmap on every property read made that call ~380ms of blocked main loop,
    which is exactly what we cannot afford (the watcher gives up after 5s)."""

    def test_reading_scalar_properties_does_not_render_the_pixmap(self):
        indicator = make_indicator(["DP-1"])

        with patch("spatricius_monitor_toggle.app.icon_pixmap_variant") as render:
            value = indicator.on_item_get_property(
                None, None, None, None, "Status"
            )

        self.assertEqual(value.unpack(), "Active")
        render.assert_not_called()

    def test_pixmap_is_rendered_once_per_icon(self):
        indicator = make_indicator(["DP-1"])

        with patch("spatricius_monitor_toggle.app.icon_pixmap_variant",
                   return_value=mock.sentinel.pixmap) as render:
            first = indicator.on_item_get_property(None, None, None, None, "IconPixmap")
            second = indicator.on_item_get_property(None, None, None, None, "IconPixmap")

        self.assertIs(first, mock.sentinel.pixmap)
        self.assertIs(second, mock.sentinel.pixmap)
        render.assert_called_once_with(ICON_BUSY)

        with patch("spatricius_monitor_toggle.app.icon_pixmap_variant",
                   return_value=mock.sentinel.other) as render:
            indicator.icon_file = ICON_OFF
            self.assertIs(
                indicator.on_item_get_property(None, None, None, None, "IconPixmap"),
                mock.sentinel.other,
            )
        render.assert_called_once_with(ICON_OFF)

    def test_unknown_property_still_answers_with_an_empty_string(self):
        indicator = make_indicator(["DP-1"])

        value = indicator.on_item_get_property(None, None, None, None, "NotAProperty")

        self.assertEqual(value.unpack(), "")


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
