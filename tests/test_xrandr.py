import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spatricius_monitor_toggle import xrandr


def output(name, enabled=True, x=0, y=0, w=1920, h=1080):
    return {
        "name": name, "enabled": enabled,
        "width": w if enabled else None, "height": h if enabled else None,
        "pos_x": x if enabled else None, "pos_y": y if enabled else None,
        "current_mode": f"{w}x{h}" if enabled else None,
        "preferred_mode": f"{w}x{h}" if enabled else None,
    }


class NeverBlankEveryScreenTests(unittest.TestCase):
    """Same guard as mutter_display_config, for the xrandr fallback backend
    (used when no Mutter/Muffin D-Bus service and no kscreen are available).
    subprocess.run is mocked throughout - this must never shell out to real
    xrandr and touch the actual display."""

    def test_refuses_when_the_only_enabled_monitor_is_selected(self):
        outputs = {"DP-1": output("DP-1", enabled=True)}
        with patch.object(xrandr, "_query_outputs", return_value=outputs), \
             patch.object(xrandr, "notify") as notify, \
             patch.object(xrandr.subprocess, "run") as run:
            xrandr.toggle_outputs(["DP-1"])

        run.assert_not_called()
        notify.assert_called_once()
        self.assertIn("Refusing to disable every active screen", notify.call_args[0][0])

    def test_refuses_when_every_currently_enabled_monitor_is_selected(self):
        outputs = {
            "DP-1": output("DP-1", enabled=True, x=0),
            "HDMI-1": output("HDMI-1", enabled=True, x=1920),
        }
        with patch.object(xrandr, "_query_outputs", return_value=outputs), \
             patch.object(xrandr, "notify") as notify, \
             patch.object(xrandr.subprocess, "run") as run:
            xrandr.toggle_outputs(["DP-1", "HDMI-1"])

        run.assert_not_called()
        notify.assert_called_once()
        self.assertIn("Refusing to disable every active screen", notify.call_args[0][0])

    def test_allows_disabling_a_subset_leaving_one_monitor_enabled(self):
        outputs = {
            "DP-1": output("DP-1", enabled=True, x=0),
            "HDMI-1": output("HDMI-1", enabled=True, x=1920),
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(xrandr, "_query_outputs", return_value=outputs), \
             patch.object(xrandr, "_pretty_names", return_value="HDMI-1"), \
             patch.object(xrandr, "notify") as notify, \
             patch.object(xrandr.subprocess, "run") as run:
            xrandr.toggle_outputs(["HDMI-1"], layout_file=Path(tmp) / "layout.json")

        run.assert_called_once()
        args = run.call_args[0][0]
        self.assertIn("--off", args)
        notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
