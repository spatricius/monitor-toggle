import unittest

from spatricius_monitor_toggle.constants import ICON_ON, ICON_OFF, ICON_BUSY
from spatricius_monitor_toggle.icon import icon_pixmap_variant


class IconPixmapVariantTests(unittest.TestCase):
    """Regression coverage for the tray-icon rendering path: past bugs here
    (see project memory) showed up as a broken/generic tray icon at runtime,
    not as an exception, so it's worth asserting the actual pixel payload
    shape rather than just "it didn't crash"."""

    def test_produces_one_32x32_argb_frame_per_icon(self):
        for icon_file in (ICON_ON, ICON_OFF, ICON_BUSY):
            with self.subTest(icon_file=icon_file):
                variant = icon_pixmap_variant(icon_file)
                frames = variant.unpack()
                self.assertEqual(len(frames), 1)
                width, height, data = frames[0]
                self.assertEqual((width, height), (32, 32))
                # ARGB, 4 bytes/pixel
                self.assertEqual(len(data), width * height * 4)


if __name__ == "__main__":
    unittest.main()
