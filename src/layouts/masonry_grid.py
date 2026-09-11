"""
Layout #7: Masonry Waterfall Grid (spec-ranked 4/8)

Gtk.FlowBox naturally staggers items across columns as space allows.
Each cell is a SkewedCard set to a small fixed skew (no scroll-driven
prominence animation here — spec notes this layout has "no continuous
animation", which keeps it cheap despite more elements being visible
at once).

Selection highlighting uses the same fix as the carousel (wallpaper_
carousel.py): Gtk.FlowBox's default selection background is a plain
rounded rectangle that doesn't match the skewed card shape drawn inside
it. Suppressed via CSS, replaced with SkewedCard's own skew-shaped
border, driven by the "selected-children-changed" signal.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .base import WallLayout
from widgets.skewed_card import SkewedCard
from widgets.thumbnail_loader import ThumbnailLoader

CELL_SKEW_DEG = -6.0  # subtler than the carousel's skew; grid density matters more here

# Same reasoning as wallpaper_carousel.py's _CSS: SkewedCard draws its own
# skewed selection border, so GTK's default FlowBoxChild selection
# rectangle needs to be suppressed to avoid a mismatched/duplicate
# highlight behind the skewed card.
_CSS = b"""
.masonry-grid flowboxchild,
.masonry-grid flowboxchild:hover,
.masonry-grid flowboxchild:selected,
.masonry-grid flowboxchild:focus,
.masonry-grid flowboxchild:active,
.masonry-grid flowboxchild.selected {
    background-color: transparent;
    background-image: none;
    background: none;
    box-shadow: none;
    outline: none;
    outline-offset: 0;
    border: none;
    border-radius: 0;
    padding: 0;
}
"""


class MasonryGridLayout(WallLayout):
    display_name = "Masonry Grid"
    performance_tier = "medium"

    def build(self) -> Gtk.Widget:
        self.loader = ThumbnailLoader()
        self._card_by_child: dict[Gtk.FlowBoxChild, SkewedCard] = {}

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)

        self.flow_box = Gtk.FlowBox()
        self.flow_box.add_css_class("masonry-grid")
        self.flow_box.set_valign(Gtk.Align.START)
        self.flow_box.set_max_children_per_line(6)
        self.flow_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow_box.set_row_spacing(12)
        self.flow_box.set_column_spacing(12)
        self.flow_box.set_margin_top(12)
        self.flow_box.set_margin_bottom(12)
        self.flow_box.set_margin_start(12)
        self.flow_box.set_margin_end(12)
        self.flow_box.connect("child-activated", self._on_child_activated)
        self.flow_box.connect("selected-children-changed", self._on_selection_changed)

        scroller.set_child(self.flow_box)
        scroller.connect("realize", self._register_css)

        return scroller

    def _register_css(self, widget):
        display = widget.get_display()
        if display is not None:
            provider = Gtk.CssProvider()
            provider.load_from_data(_CSS)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

    def _apply_wallpapers(self, paths: list[str]):
        child = self.flow_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.flow_box.remove(child)
            child = next_child
        self._card_by_child.clear()

        for path in paths:
            card = SkewedCard(skew_deg=CELL_SKEW_DEG, base_width=140, base_height=180)
            card.animations_enabled = False  # static grid, no prominence animation
            card_holder = Gtk.FlowBoxChild()
            card_holder.set_child(card)
            card_holder.wallpaper_path = path  # stash for lookup on activation
            self.flow_box.append(card_holder)
            self._card_by_child[card_holder] = card

            def on_ready(item_id, texture, card=card):
                card.texture = texture

            self.loader.request(path, path, on_ready)

    def _on_child_activated(self, flow_box, child):
        path = getattr(child, "wallpaper_path", None)
        if path:
            self.emit("wallpaper-selected", path)

    def _on_selection_changed(self, flow_box):
        selected = set(flow_box.get_selected_children())
        for child, card in self._card_by_child.items():
            card.set_selected(child in selected)
