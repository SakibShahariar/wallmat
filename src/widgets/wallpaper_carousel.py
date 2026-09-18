"""
WallpaperCarousel: horizontal Gtk.ListView over a Gio.ListStore of
WallpaperItem, rendering SkewedCard widgets. Virtualized by GTK4's
ListView (only visible + small buffer of items are realized).

Center-active scaling: listens to the internal ScrolledWindow's
Gtk.Adjustment and, on every value-changed, recomputes each *visible*
item's distance from the viewport center and feeds that into
SkewedCard.set_prominence(). This is the main per-frame cost during
scroll and is exactly what the FPS benchmark should stress.
"""

import itertools

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject, Gdk

from .skewed_card import SkewedCard, natural_width
from .thumbnail_loader import ThumbnailLoader
from .gsk_utils import hide_scrollbars, get_animations_enabled, watch_animations_enabled
from announce import say

_item_id_counter = itertools.count()

CARD_WIDTH = 130  # smaller cards = more visible at once in the strip;
                   # keep in sync with SkewedCard base_width for center-math
CARD_NATURAL_WIDTH = natural_width(CARD_WIDTH, int(CARD_WIDTH * 1.3))  # includes
                   # skew_pad — see skewed_card.py's natural_width() docstring

# Suppresses GTK's default rectangular row-selection highlight, since
# SkewedCard now draws its own skew-shaped selection border instead —
# without this, you'd see both: GTK's plain rectangle behind our skewed
# card. Covering both "row" and "listitem" node names plus several
# pseudo-class/state-class forms defensively, since GTK4's exact internal
# CSS node naming for ListView rows has shifted across minor versions and
# isn't something we can verify without a live GTK4 environment here.
_CSS = b"""
.wallpaper-carousel row,
.wallpaper-carousel row:hover,
.wallpaper-carousel row:selected,
.wallpaper-carousel row:focus,
.wallpaper-carousel row:active,
.wallpaper-carousel row.selected,
.wallpaper-carousel listitem,
.wallpaper-carousel listitem:hover,
.wallpaper-carousel listitem:selected,
.wallpaper-carousel listitem:focus,
.wallpaper-carousel listitem:active,
.wallpaper-carousel listitem.selected {
    background-color: transparent;
    background-image: none;
    background: none;
    box-shadow: none;
    outline: none;
    outline-offset: 0;
    border: none;
    border-radius: 0;
    padding: 0;
    margin: 0;
}

/* Hide the horizontal scrollbar under the strip. Scrolling still works
   (wheel/arrows/trackpad drive the adjustment); only the visual bar is
   removed. Scoped to the .hide-scrollbar class so the display-global
   provider does not affect other apps' scrollbars. */
.hide-scrollbar scrollbar,
.hide-scrollbar scrollbar hover,
.hide-scrollbar scrollbar:disabled,
.hide-scrollbar scrollbar trough,
.hide-scrollbar scrollbar trough:backdrop,
.hide-scrollbar scrollbar slider,
.hide-scrollbar scrollbar slider:hover,
.hide-scrollbar scrollbar slider:disabled {
    min-width: 0;
    min-height: 0;
    margin: 0;
    padding: 0;
    background: none;
    background-image: none;
    border: none;
    box-shadow: none;
    outline: none;
}
"""


class WallpaperItem(GObject.Object):
    __gtype_name__ = "WallpaperItem"

    path = GObject.Property(type=str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        # A path-only id collides whenever the same path appears more
        # than once in the underlying model — which Infinite Ribbon does
        # deliberately (paths * 3, for the loop illusion). That collision
        # broke the selection-border tracking in _on_selection_changed
        # below, since _live_widgets is keyed by item_id: multiple
        # simultaneously-bound cards sharing one path would overwrite
        # each other's dictionary entry. Appending a per-instance counter
        # keeps item_id unique even when paths repeat.
        self.item_id = f"{path}:{next(_item_id_counter)}"
        self.texture = None  # populated async by ThumbnailLoader


class WallpaperCarousel(Gtk.Box):
    __gtype_name__ = "WallpaperCarousel"

    __gsignals__ = {
        "wallpaper-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, fill_height: bool = False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        # When True, cards stretch to fill whatever vertical space the
        # carousel is given (used by Infinite Ribbon, which shouldn't
        # have dead space above/below). When False (default), cards stay
        # at their small fixed size, centered — used by Split-Screen,
        # where the carousel is a compact strip below a preview pane and
        # shouldn't balloon to fill the remaining space.
        self._fill_height = fill_height

        self.store = Gio.ListStore(item_type=WallpaperItem)
        # Infinite Ribbon's fill_height cards can stretch to most of the
        # window's height; the compact strip layouts (Split-Screen) never
        # exceed CARD_WIDTH~130px wide. One shared 900px constant used to
        # cover both cases; sizing per-instance instead means the compact
        # strip isn't paying decode/cache/memory cost for resolution it
        # never displays.
        self.loader = ThumbnailLoader(thumb_size=900 if fill_height else 420)
        self.animations_enabled = True

        # track which SkewedCard widget currently represents which item_id,
        # so async thumbnail delivery can find the right widget even after
        # ListView recycling has moved things around.
        self._live_widgets: dict[str, SkewedCard] = {}
        # item_id currently under keyboard focus (drives the inset focus
        # ring on the live card) — separate from _live_widgets selection.
        self._focused_item: str | None = None

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        factory.connect("unbind", self._on_unbind)

        self.selection = Gtk.SingleSelection(model=self.store)
        self.selection.set_autoselect(False)
        self.selection.connect("selection-changed", self._on_selection_changed)

        self.list_view = Gtk.ListView(model=self.selection, factory=factory)
        self.list_view.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.list_view.add_css_class("wallpaper-carousel")

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.add_css_class("hide-scrollbar")
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.scroller.set_hexpand(True)
        if self._fill_height:
            self.scroller.set_vexpand(True)
        self.scroller.set_child(self.list_view)
        self.append(self.scroller)

        self.scroller.connect("realize", self._register_css)

        # Center-active scaling: react to horizontal scroll position.
        self._hadjustment = self.scroller.get_hadjustment()
        self._hadjustment.connect("value-changed", self._on_scroll_changed)

        self._watch_animation_setting()

    def _register_css(self, widget):
        display = widget.get_display()
        if display is not None:
            hide_scrollbars(self.scroller)
            provider = Gtk.CssProvider()
            provider.load_from_data(_CSS)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
            say("[wallpaper_carousel] row-selection CSS registered")
        else:
            say("[wallpaper_carousel] WARNING: no display available, CSS not registered")

    # -- public API --

    def load_wallpapers(self, paths: list[str]):
        # Bulk-splice instead of appending one at a time: appending in a
        # loop fires a separate items-changed (and, with autoselect on,
        # a selection-changed) for every single item, which is what
        # caused "wallpaper-selected" to spam for the whole folder on load.
        items = [WallpaperItem(path) for path in paths]
        self.store.splice(0, self.store.get_n_items(), items)

    # -- factory callbacks --

    def _on_setup(self, factory, list_item):
        card = SkewedCard(base_width=CARD_WIDTH, base_height=int(CARD_WIDTH * 1.3))
        card.animations_enabled = self.animations_enabled
        # Without explicit alignment, GTK4's ListView stretches items to
        # fill available space rather than honoring do_measure's fixed
        # size — this is what was causing cards to divide the window
        # width evenly with no gaps instead of sitting at a fixed size.
        card.set_halign(Gtk.Align.CENTER)
        if self._fill_height:
            # Let the card stretch vertically to fill the row instead of
            # sitting at a small fixed height with dead space around it.
            card.set_valign(Gtk.Align.FILL)
            card.set_vexpand(True)
        else:
            card.set_valign(Gtk.Align.CENTER)
            card.set_vexpand(False)
        card.set_hexpand(False)
        card.set_margin_start(6)
        card.set_margin_end(6)
        list_item.set_child(card)

    def _on_bind(self, factory, list_item):
        item: WallpaperItem = list_item.get_item()
        card: SkewedCard = list_item.get_child()

        self._live_widgets[item.item_id] = card

        if item.texture is not None:
            card.texture = item.texture
        else:
            card.texture = None

            def on_ready(item_id, texture):
                # Guard against delivery after the widget has been recycled
                # to a different item (fast scroll past a pending request).
                if self._live_widgets.get(item_id) is not card:
                    return
                item.texture = texture
                card.texture = texture

            self.loader.request(item.item_id, item.path, on_ready)

        selected_item = self.selection.get_selected_item()
        card.set_selected(selected_item is item)
        card.set_focused(self._focused_item is not None and self._focused_item == item.item_id)

        self._recompute_prominence()

    def _on_unbind(self, factory, list_item):
        item: WallpaperItem = list_item.get_item()
        card: SkewedCard = list_item.get_child()

        if item is not None:
            self.loader.cancel(item.item_id)
            if self._live_widgets.get(item.item_id) is card:
                del self._live_widgets[item.item_id]

        # Release the GPU texture reference for this recycled slot.
        card.texture = None
        card.set_focused(False)

    def _on_selection_changed(self, selection, position, n_items):
        item = self.selection.get_selected_item()
        # Update the highlight border on every currently-live card, not
        # just the newly-selected one — the previously-selected card (if
        # still bound/visible) needs its border cleared too.
        for item_id, card in self._live_widgets.items():
            card.set_selected(item is not None and item.item_id == item_id)
        if item is not None:
            self.emit("wallpaper-selected", item.path)

    def set_focus(self, item_id: str | None):
        """Move the keyboard-focus ring to a different card. Purely
        visual (matching set_selected's live-widget sweep): arrows move
        focus without touching the ListView selection, so Enter/click
        remain the only ways to actually select."""
        self._focused_item = item_id
        for live_id, card in self._live_widgets.items():
            card.set_focused(live_id == item_id)

    # -- center-active scaling --

    def _on_scroll_changed(self, adjustment):
        self._recompute_prominence()

    def _recompute_prominence(self):
        """
        For every currently-live (bound) card, compute how close its
        estimated position is to the viewport center and set prominence
        accordingly. This runs on every scroll tick, so keep it cheap —
        no allocation, no widget tree walks beyond the live_widgets dict.
        """
        viewport_width = self.scroller.get_width()
        if viewport_width <= 0:
            return
        scroll_x = self._hadjustment.get_value()
        viewport_center = scroll_x + viewport_width / 2.0

        for item_id, card in self._live_widgets.items():
            allocation = card.get_allocation()
            card_center = allocation.x + allocation.width / 2.0
            distance = abs(card_center - viewport_center)
            # Falloff: fully prominent within ~half a card width of center,
            # fading to 0 by 2 card widths away. Uses the corrected
            # natural width (includes skew padding) rather than the bare
            # CARD_WIDTH — the falloff curve was slightly tighter than
            # intended before this, though the underlying "which card is
            # actually closest to center" distance math uses real
            # get_allocation() data, so this specifically affects the
            # falloff steepness, not which card gets identified as most
            # prominent.
            falloff_range = CARD_NATURAL_WIDTH * 1.5
            prominence = max(0.0, 1.0 - (distance / falloff_range))
            card.set_prominence(prominence)

    # -- animation setting --

    def _watch_animation_setting(self):
        # get_animations_enabled()/watch_animations_enabled() never raise —
        # unlike a bare Gio.Settings.new("org.gnome.desktop.interface"),
        # which throws GLib.Error and takes down carousel construction on
        # any system missing that schema (non-GNOME desktops, minimal
        # containers). This app's own custom GSettings schema already has
        # a fallback for exactly this case (see window.py's
        # _LayoutPreference); this brings the animation-setting read up to
        # the same standard.
        self.animations_enabled = get_animations_enabled()

        def on_changed(enabled):
            self.animations_enabled = enabled
            for card in self._live_widgets.values():
                card.animations_enabled = enabled
                card.queue_draw()

        # None if the schema isn't available here — self.animations_enabled
        # just keeps its one-shot default and won't live-update, which is a
        # reasonable degradation rather than a crash.
        self._interface_settings = watch_animations_enabled(on_changed)
