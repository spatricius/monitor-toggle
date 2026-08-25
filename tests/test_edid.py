import unittest

from spatricius_monitor_toggle.edid import (
    _name_from_edid_bytes, read_edid_name_from_hex,
)


def _descriptor(tag, payload=b""):
    """Build one 18-byte EDID descriptor block. `tag` selects the type
    (0xFC = monitor name); `payload` is the raw text for name-type blocks."""
    body = payload[:13].ljust(13, b" ")
    return bytes([0x00, 0x00, 0x00, tag, 0x00]) + body


def _edid(descriptors):
    header = bytes(54)
    blocks = b"".join(descriptors[:4]).ljust(4 * 18, b"\x00")
    return (header + blocks).ljust(128, b"\x00")


class NameFromEdidBytesTests(unittest.TestCase):
    def test_too_short_returns_none(self):
        self.assertIsNone(_name_from_edid_bytes(b"\x00" * 100))

    def test_extracts_monitor_name_descriptor(self):
        data = _edid([_descriptor(0xFC, b"MyMonitor\n")])
        self.assertEqual(_name_from_edid_bytes(data), "MyMonitor")

    def test_strips_trailing_padding_and_newline(self):
        data = _edid([_descriptor(0xFC, b"Dell U2720Q\n ")])
        self.assertEqual(_name_from_edid_bytes(data), "Dell U2720Q")

    def test_skips_non_name_descriptors_and_finds_the_right_one(self):
        data = _edid([_descriptor(0xFF, b"SomeSerial"), _descriptor(0xFC, b"LG Monitor\n")])
        self.assertEqual(_name_from_edid_bytes(data), "LG Monitor")

    def test_no_name_descriptor_returns_none(self):
        data = _edid([_descriptor(0xFD, b"range limits")])
        self.assertIsNone(_name_from_edid_bytes(data))

    def test_blank_name_descriptor_returns_none(self):
        data = _edid([_descriptor(0xFC, b"\n")])
        self.assertIsNone(_name_from_edid_bytes(data))


class ReadEdidNameFromHexTests(unittest.TestCase):
    def test_valid_hex_round_trips_to_name(self):
        data = _edid([_descriptor(0xFC, b"HDMI Display\n")])
        self.assertEqual(read_edid_name_from_hex(data.hex()), "HDMI Display")

    def test_invalid_hex_returns_none(self):
        self.assertIsNone(read_edid_name_from_hex("not-hex-at-all"))


if __name__ == "__main__":
    unittest.main()
