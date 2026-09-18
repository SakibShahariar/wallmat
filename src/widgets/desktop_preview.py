"""
DesktopPreview: shows the currently selected wallpaper, full-bleed.

Earlier versions drew a mock GNOME top bar + dock over the wallpaper to
simulate real desktop chrome. Removed — it kept reading as an unwanted
overlay/rendering artifact rather than helpful mock chrome, even after
making it fully opaque instead of semi-transparent. A clean, unobstructed
preview of the wallpaper itself is what's actually wanted here.

Decoding happens on a background thread: set_wallpaper_path() fires right
when the user commits a selection (Enter/click) — the one moment the app
most needs to feel responsive — so a synchronous, main-thread GdkPixbuf
decode here would put a stutter exactly where a user is most likely to
notice one. A `_generation` counter guards against a slow decode from an
earlier selection landing after a newer one, in case the user selects
again before the first decode finishes.
"""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Graphene

from .gsk_utils import draw_texture_cover


class DesktopPreview(Gtk.Widget):
    __gtype_name__ = "DesktopPreview"

    def __init__(self):
        super().__init__()
        self._texture: Gdk.Texture | None = None
        self._generation = 0
        self.set_vexpand(True)
        self.set_hexpand(True)

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 320, 480, -1, -1
        return 200, 300, -1, -1

    def set_wallpaper_path(self, path: str):
        self._generation += 1
        my_generation = self._generation

        def decode_worker():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            except Exception:
                pixbuf = None
            GLib.idle_add(self._deliver, my_generation, pixbuf)

        threading.Thread(target=decode_worker, daemon=True).start()

    def _deliver(self, generation: int, pixbuf):
        if generation != self._generation:
            return GLib.SOURCE_REMOVE  # a newer selection has since superseded this one
        self._texture = Gdk.Texture.new_for_pixbuf(pixbuf) if pixbuf is not None else None
        self.queue_draw()
        return GLib.SOURCE_REMOVE

    def do_snapshot(self, snapshot: Gtk.Snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return

        if self._texture is not None:
            # Cover fit: crop to fill the preview area without distorting
            # the wallpaper's aspect ratio.
            draw_texture_cover(snapshot, self._texture, 0, 0, width, height)
        else:
            bg_rect = Graphene.Rect().init(0, 0, width, height)
            placeholder = Gdk.RGBA()
            placeholder.parse("#1e1e1e")
            snapshot.append_color(placeholder, bg_rect)
