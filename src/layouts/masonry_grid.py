"""
Layout #7: Masonry Waterfall Grid (spec-ranked 4/8).

Gtk.GridView virtualizes wallpaper cells: GTK creates and binds cards for
items around the viewport instead of constructing one widget per path.
Thumbnail decoding starts on bind and is cancelled on unbind when no
texture has been produced, keeping large collections responsive.
"""
import itertools

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from .base import WallLayout
from widgets.skewed_card import SkewedCard
from widgets.thumbnail_loader import ThumbnailLoader
from widgets.gsk_utils import hide_scrollbars

CELL_SKEW_DEG = -6.0
_item_id_counter = itertools.count()

_CSS = b"""
.masonry-grid > child,
.masonry-grid > child:hover,
.masonry-grid > child:selected,
.masonry-grid > child:focus,
.masonry-grid > child:active,
.masonry-grid > child.selected,
.masonry-grid listitem,
.masonry-grid listitem:hover,
.masonry-grid listitem:selected,
.masonry-grid listitem:focus,
.masonry-grid listitem:active,
.masonry-grid listitem.selected {
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


class MasonryItem(GObject.Object):
    __gtype_name__ = "MasonryItem"
    path = GObject.Property(type=str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.item_id = f"{path}:{next(_item_id_counter)}"
        self.texture = None


class MasonryGridLayout(WallLayout):
    display_name = "Masonry Grid"
    performance_tier = "medium"

    def build(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.set_vexpand(True)
        outer.set_hexpand(True)

        self.store = Gio.ListStore(item_type=MasonryItem)
        self.loader = ThumbnailLoader(thumb_size=360)
        self._live_widgets: dict[str, SkewedCard] = {}

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        factory.connect("unbind", self._on_unbind)

        self.selection = Gtk.SingleSelection(model=self.store)
        self.selection.set_autoselect(False)
        self.selection.connect("selection-changed", self._on_selection_changed)

        self.grid_view = Gtk.GridView(model=self.selection, factory=factory)
        self.grid_view.add_css_class("masonry-grid")
        self.grid_view.set_min_columns(1)
        self.grid_view.set_max_columns(6)
        # Gtk.GridView has no row/column spacing setters. Keep the gutters
        # on each recycled cell instead of calling Gtk.Grid-only methods.
        # The window treats activation as selecting a wallpaper; keep that
        # action consistent with the layout's single-click selection hint.
        self.grid_view.set_single_click_activate(True)
        self.grid_view.connect("activate", self._on_item_activated)

        scroller = Gtk.ScrolledWindow()
        scroller.add_css_class("hide-scrollbar")
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)
        scroller.set_child(self.grid_view)
        scroller.connect("realize", self._register_css)
        outer.append(scroller)

        hint = Gtk.Label(label="Click a wallpaper to select it")
        hint.add_css_class("dim-label")
        hint.set_margin_bottom(6)
        outer.append(hint)
        return outer

    def _register_css(self, widget):
        display = widget.get_display()
        if display is not None:
            hide_scrollbars(widget)
            provider = Gtk.CssProvider()
            provider.load_from_data(_CSS)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

    def _apply_wallpapers(self, paths: list[str]):
        # A single model splice avoids rebuilding a widget for every path.
        items = [MasonryItem(path) for path in paths]
        self.store.splice(0, self.store.get_n_items(), items)

    def select_path(self, path: str) -> bool:
        """Restore the selected grid item when the saved path is still present."""
        try:
            position = self._paths.index(path)
        except ValueError:
            return False
        self.selection.set_selected(position)
        self.grid_view.grab_focus()
        return True

    def _on_setup(self, factory, list_item):
        card = SkewedCard(
            skew_deg=CELL_SKEW_DEG, base_width=140, base_height=180
        )
        card.animations_enabled = False
        card.set_halign(Gtk.Align.CENTER)
        for side in ("start", "end", "top", "bottom"):
            getattr(card, f"set_margin_{side}")(6)
        list_item.set_child(card)

    def _on_bind(self, factory, list_item):
        item: MasonryItem = list_item.get_item()
        card: SkewedCard = list_item.get_child()
        if item is None or card is None:
            return

        self._live_widgets[item.item_id] = card
        card.texture = item.texture
        card.set_selected(self.selection.get_selected_item() is item)

        if item.texture is None:
            def on_ready(item_id, texture, item=item, card=card):
                # GridView recycles list items; reject stale async deliveries.
                if self._live_widgets.get(item_id) is not card:
                    return
                item.texture = texture
                card.texture = texture

            self.loader.request(item.item_id, item.path, on_ready)

    def _on_unbind(self, factory, list_item):
        item = list_item.get_item()
        card = list_item.get_child()
        if item is not None:
            self.loader.cancel(item.item_id)
            if self._live_widgets.get(item.item_id) is card:
                del self._live_widgets[item.item_id]
        if card is not None:
            card.texture = None
            card.set_selected(False)

    def _on_item_activated(self, grid_view, position):
        item = self.store.get_item(position)
        if item is not None:
            self.emit("wallpaper-selected", item.path)

    def _on_selection_changed(self, selection, position, n_items):
        selected_item = selection.get_selected_item()
        for item_id, card in self._live_widgets.items():
            card.set_selected(
                selected_item is not None and selected_item.item_id == item_id
            )
