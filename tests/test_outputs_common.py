import unittest

from spatricius_monitor_toggle.outputs_common import (
    selected_outputs_enabled, selected_output_infos,
    output_label, output_short_label, output_pretty_name, pretty_names,
)


def make_output(name, enabled):
    return {"name": name, "enabled": enabled, "label": name, "short_label": name}


class SelectedOutputsEnabledTests(unittest.TestCase):
    def test_true_when_all_selected_outputs_are_enabled(self):
        outputs = [make_output("DP-1", True), make_output("HDMI-1", False)]
        self.assertTrue(selected_outputs_enabled(outputs, ["DP-1"]))

    def test_false_when_any_selected_output_is_disabled(self):
        outputs = [make_output("DP-1", True), make_output("HDMI-1", False)]
        self.assertFalse(selected_outputs_enabled(outputs, ["DP-1", "HDMI-1"]))

    def test_false_when_selected_output_is_not_present_at_all(self):
        outputs = [make_output("HDMI-1", True)]
        self.assertFalse(selected_outputs_enabled(outputs, ["DP-1"]))

    def test_false_when_no_outputs(self):
        self.assertFalse(selected_outputs_enabled([], ["DP-1"]))


class SelectedOutputInfosTests(unittest.TestCase):
    def test_returns_only_matching_outputs(self):
        outputs = [make_output("DP-1", True), make_output("HDMI-1", False)]
        infos = selected_output_infos(outputs, ["HDMI-1"])
        self.assertEqual([o["name"] for o in infos], ["HDMI-1"])

    def test_empty_when_selected_output_not_present(self):
        outputs = [make_output("HDMI-1", True)]
        self.assertEqual(selected_output_infos(outputs, ["DP-1"]), [])


class OutputLabelTests(unittest.TestCase):
    def test_uses_model_name_with_resolution_and_scale(self):
        label = output_label("DP-1", "Dell U2720Q", {"width": 2560, "height": 1440}, 1.5)
        self.assertEqual(label, "Dell U2720Q (2560 x 1440, 150%)")

    def test_falls_back_to_connector_name_when_no_model_name(self):
        label = output_label("DP-1", None, {"width": 1920, "height": 1080}, 1)
        self.assertEqual(label, "DP-1 (1920 x 1080, 100%)")

    def test_omits_resolution_when_size_is_empty(self):
        label = output_label("DP-1", "Dell U2720Q", {}, 1)
        self.assertEqual(label, "Dell U2720Q")

    def test_omits_resolution_when_only_width_known(self):
        label = output_label("DP-1", "Dell U2720Q", {"width": 1920}, 1)
        self.assertEqual(label, "Dell U2720Q")

    def test_rounds_fractional_scale_percentage(self):
        label = output_label("DP-1", "Monitor", {"width": 1, "height": 1}, 1.333)
        self.assertEqual(label, "Monitor (1 x 1, 133%)")


class OutputShortLabelTests(unittest.TestCase):
    def test_uses_model_name_when_present(self):
        self.assertEqual(output_short_label("DP-1", "Dell U2720Q"), "Dell U2720Q")

    def test_falls_back_to_connector_name(self):
        self.assertEqual(output_short_label("DP-1", None), "DP-1")


class PrettyNamesTests(unittest.TestCase):
    def test_uses_lookup_result_when_available(self):
        lookup = {"DP-1": "Dell U2720Q"}.get
        self.assertEqual(output_pretty_name(lookup, "DP-1"), "Dell U2720Q")

    def test_falls_back_to_raw_name_when_lookup_misses(self):
        lookup = {}.get
        self.assertEqual(output_pretty_name(lookup, "DP-1"), "DP-1")

    def test_joins_multiple_names(self):
        lookup = {"DP-1": "Dell U2720Q"}.get
        self.assertEqual(pretty_names(lookup, ["DP-1", "HDMI-1"]), "Dell U2720Q, HDMI-1")


if __name__ == "__main__":
    unittest.main()
