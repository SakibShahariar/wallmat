"""
Layout #3: Split-Screen Preview (spec's RECOMMENDED layout)

Top: desktop mockup with the selected wallpaper, expands to fill all
available space. Bottom: the skewed thumbnail carousel, fixed height,
pinned flush to the bottom edge.

A plain vertical Gtk.Box, not Gtk.Paned — Paned implies a user-draggable
divider, which isn't the actual use case here, and an earlier version
using Paned with a fixed pixel position (calibrated for one specific
window height) left dead black space between the carousel's actual
content height and the divider whenever the window was taller than that
one calibration point. A vexpand child in a Box automatically claims all
leftover space with no such gap, regardless of window height.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

from .base import WallLayout
from announce import say
from widgets.wallpaper_carousel import WallpaperCarousel, CARD_WIDTH
from widgets.skewed_card import natural_width
from widgets.desktop_preview import DesktopPreview

CARD_STRIDE = natural_width(CARD_WIDTH, int(CARD_WIDTH * 1.3)) + 12


class SplitScreenLayout(WallLayout):
    display_name = "Split-Screen Preview"
    performance_tier = "fast"

    def build(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_vexpand(True)
        outer.set_hexpand(True)

        self.preview = DesktopPreview()
        self.preview.set_vexpand(True)
        self.preview.set_hexpand(True)
        outer.append(self.preview)

        self.carousel = WallpaperCarousel()
        # No fixed height: let the strip size to its natural card height
        # (~169px). A previous hardcoded 190px min-height left ~21px of
        # vertical slack that accumulated BELOW the cards, i.e. a visible
        # gap between the strip and the window's bottom edge. Letting the
        # carousel hug its content removes the magic number entirely.
        self.carousel.connect("wallpaper-selected", self._on_selected)
        outer.append(self.carousel)

        self._focus: int | None = None
        # Intercept Left/Right/Enter in CAPTURE phase ON THE LISTVIEW, so
        # GtkListView's own built-in arrow handling never gets a chance to
        # run. In bubble phase on `outer`, the keystroke first reached the
        # focused ListView, whose native Left/Right moves the
        # Gtk.SingleSelection — which fired wallpaper-selected on mere
        # arrow navigation ("first wallpaper auto-selected"). Same class
        # of bug infinite_ribbon's docstring documents; CAPTURE + consume
        # keeps every position/selection change on our one code path.
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_key_pressed)
        self.carousel.list_view.add_controller(controller)

        hint = Gtk.Label(label="← / → to browse, Enter or click to select")
        hint.add_css_class("dim-label")
        hint.set_margin_top(4)
        hint.set_margin_bottom(6)
        outer.append(hint)

        # Without a focus grab the Left/Right controller above never sees
        # keystrokes until the user happens to click a card, which made the
        # strip look stuck on its first few items.
        self.carousel.list_view.connect("realize", lambda w: w.grab_focus())

        # Keep focus (and therefore the big preview) in sync with the card
        # the user scrolls to with the mouse wheel or trackpad.
        self.carousel.scroller.get_hadjustment().connect(
            "value-changed", self._on_scroll
        )

        return outer

    def on_activate(self):
        self.carousel.list_view.grab_focus()

    def _apply_wallpapers(self, paths: list[str]):
        self.carousel.load_wallpapers(paths)
        if paths:
            self._set_focus(0, announce=False)

    def select_path(self, path: str) -> bool:
        """Restore keyboard focus and horizontal visibility for a saved path."""
        try:
            position = self._paths.index(path)
        except ValueError:
            return False
        self._set_focus(position, announce=False)
        return True

    def _set_focus(self, position: int, announce: bool = True, scroll: bool = True):
        n = self.carousel.store.get_n_items()
        if not n:
            return
        position = max(0, min(n - 1, position))
        item = self.carousel.store.get_item(position)
        self._focus = position
        if scroll:
            try:
                self.carousel.list_view.scroll_to(
                    position, Gtk.ListScrollFlags.FOCUS, None
                )
            except Exception:
                pass
        self.carousel.set_focus(item.item_id)
        # The large preview follows the focused wallpaper, not only the
        # committed selection. Arrow-key browsing and scrolling now both
        # update it immediately.
        self.preview.set_wallpaper_path(item.path)
        if announce:
            say(f"Focus: {item.path}")

    def _on_scroll(self, adjustment):
        n = self.carousel.store.get_n_items()
        viewport_width = self.carousel.scroller.get_width()
        if not n or viewport_width <= 0:
            return
        center = adjustment.get_value() + viewport_width / 2.0
        position = round(center / CARD_STRIDE - 0.5)
        position = max(0, min(n - 1, position))
        if position != self._focus:
            # Do not scroll back — that would feed back into value-changed.
            self._set_focus(position, announce=False, scroll=False)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            if not self.carousel.store.get_n_items():
                return True
            if self._focus is None:
                self._focus = 0
            step = 1 if keyval == Gdk.KEY_Right else -1
            self._set_focus(self._focus + step)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._focus is not None:
                self.carousel.selection.set_selected(self._focus)
            return True
        return False

    def _on_selected(self, carousel, path):
        self.preview.set_wallpaper_path(path)
        self.emit("wallpaper-selected", path)
