"""
DesktopPreview: shows the currently selected wallpaper, full-bleed.

Earlier versions drew a mock GNOME top bar + dock over the wallpaper to
simulate real desktop chrome. Removed — it kept reading as an unwanted
overlay/rendering artifact rather than helpful mock chrome, even after
making it fully opaque instead of semi-transparent. A clean, unobstructed
preview of the wallpaper itself is what's actually wanted here.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf

from .gsk_utils import draw_texture_cover


class DesktopPreview(Gtk.Widget):
    __gtype_name__ = "DesktopPreview"

    def __init__(self):
        super().__init__()
        self._texture: Gdk.Texture | None = None
        self.set_vexpand(True)
        self.set_hexpand(True)

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 320, 480, -1, -1
        return 200, 300, -1, -1

    def set_wallpaper_path(self, path: str):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            self._texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            self._texture = None
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return

        from gi.repository import Graphene

        if self._texture is not None:
            # Cover fit: crop to fill the preview area without distorting
            # the wallpaper's aspect ratio.
            draw_texture_cover(snapshot, self._texture, 0, 0, width, height)
        else:
            bg_rect = Graphene.Rect().init(0, 0, width, height)
            placeholder = Gdk.RGBA()
            placeholder.parse("#1e1e1e")
            snapshot.append_color(placeholder, bg_rect)
