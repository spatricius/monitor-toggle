import tempfile
import unittest
from pathlib import Path

from spatricius_monitor_toggle.config import (
    load_config, save_config, load_selected_outputs, save_selected_outputs,
)
from spatricius_monitor_toggle.constants import DEFAULT_OUTPUT


class ConfigRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_load_config_missing_file_defaults_false(self):
        self.assertFalse(load_config(self.dir / "config.json"))

    def test_save_and_load_config_round_trip(self):
        path = self.dir / "config.json"
        save_config(True, path)
        self.assertTrue(load_config(path))
        save_config(False, path)
        self.assertFalse(load_config(path))

    def test_load_selected_outputs_missing_file_defaults_to_default_output(self):
        self.assertEqual(
            load_selected_outputs(self.dir / "selected.json"), [DEFAULT_OUTPUT]
        )

    def test_load_selected_outputs_garbage_file_defaults_to_default_output(self):
        path = self.dir / "selected.json"
        path.write_text("not json")
        self.assertEqual(load_selected_outputs(path), [DEFAULT_OUTPUT])

    def test_save_and_load_selected_outputs_round_trip(self):
        path = self.dir / "selected.json"
        save_selected_outputs(["HDMI-1", "DP-2"], path)
        self.assertEqual(load_selected_outputs(path), ["HDMI-1", "DP-2"])

    def test_save_selected_outputs_preserved_even_if_currently_disconnected(self):
        # save_selected_outputs / load_selected_outputs never consult which
        # monitors are physically connected - persistence is dumb storage,
        # so a name for a currently-unplugged monitor round-trips unchanged.
        path = self.dir / "selected.json"
        save_selected_outputs(["Unplugged-Monitor"], path)
        self.assertEqual(load_selected_outputs(path), ["Unplugged-Monitor"])


if __name__ == "__main__":
    unittest.main()
