import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib


def icon_pixmap_variant(icon_file):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_file, 32, 32, True)
    if pixbuf is None:
        return GLib.Variant("a(iiay)", [])
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    pixels = pixbuf.get_pixels()
    data = bytearray()

    for y in range(height):
        row = y * rowstride
        for x in range(width):
            offset = row + x * channels
            red = pixels[offset]
            green = pixels[offset + 1]
            blue = pixels[offset + 2]
            alpha = pixels[offset + 3] if channels == 4 else 255
            data.extend((alpha, red, green, blue))

    return GLib.Variant("a(iiay)", [(width, height, bytes(data))])
