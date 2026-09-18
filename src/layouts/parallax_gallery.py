"""
Layout #6: Horizontal Parallax Gallery (spec-ranked 6/8)

Two independently-scrollable Gtk.ScrolledWindow instances stacked in an
Overlay: a background layer of large, blurred/dimmed images that scrolls
at 0.3x, and a foreground layer of sharp thumbnails that scrolls at 1.0x
(driven by the user's actual scroll input). The foreground's Gtk.Adjustment
is the "driver" — its value-changed signal repositions the background
adjustment proportionally, which is the standard way to fake a parallax
effect in GTK4 since there's no native multi-speed-scroll primitive.

Both layers route through ThumbnailLoader (async, background-thread
decode, downscaled, cached) — an earlier version called
Gtk.Picture.set_filename() directly, which does a SYNCHRONOUS,
main-thread-blocking, full-resolution decode with no caching. With two
separate layers eagerly binding multiple large wallpapers each on
launch, that was causing multi-second (reported: ~40s) launch freezes.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GObject, GLib

from .base import WallLayout
from announce import say
from widgets.thumbnail_loader import ThumbnailLoader
from widgets.gsk_utils import hide_scrollbars

PARALLAX_RATIO = 0.3
FG_ITEM_WIDTH = 180
FG_ITEM_MARGIN = 12  # 6px each side
FG_STRIDE = FG_ITEM_WIDTH + FG_ITEM_MARGIN  # per-item scroll increment, an estimate

_CSS_TEMPLATE = b"""
.parallax-fg {
    border-radius: 12px;
}
.parallax-fg.focused {
    box-shadow: 0 0 0 3px {ring};
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


class _ParallaxItem(GObject.Object):
    path = GObject.Property(type=str)

    def __init__(self, path):
        super().__init__()
        self.path = path


class ParallaxGalleryLayout(WallLayout):
    display_name = "Parallax Gallery"
    performance_tier = "medium"

    def __init__(self):
        super().__init__()
        # Keyboard navigation moves focus only; selection (and the
        # wallpaper-selected emission that prints "Selected:") happens
        # exclusively on Enter or a click.
        self._focus = None
        self._live_fg: dict[str, Gtk.Picture] = {}  # path -> currently-bound fg picture

    def build(self) -> Gtk.Widget:
        # Two separate loader instances, not one shared — the same path
        # appears in BOTH bg_store and fg_store, and ThumbnailLoader.
        # request() cancels any prior pending request sharing the same
        # item_id. A single shared loader keyed by plain path would let a
        # foreground request silently cancel the background request for
        # that same image (or vice versa), leaving one layer stuck blank.
        self.bg_loader = ThumbnailLoader()
        self.fg_loader = ThumbnailLoader()

        overlay = Gtk.Overlay()
        overlay.set_vexpand(True)
        overlay.set_hexpand(True)

        # Background layer: larger, dimmed images
        self.bg_store = Gio.ListStore(item_type=_ParallaxItem)
        bg_factory = Gtk.SignalListItemFactory()
        bg_factory.connect("setup", self._on_bg_setup)
        bg_factory.connect("bind", self._on_bg_bind)
        self.bg_view = Gtk.ListView(
            model=Gtk.NoSelection(model=self.bg_store), factory=bg_factory
        )
        self.bg_view.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.bg_view.set_can_target(False)  # background never receives input directly
        self.bg_scroller = Gtk.ScrolledWindow()
        # The ScrolledWindow itself owns/processes scroll-wheel input
        # independently of its child — marking only bg_view non-
        # targetable wasn't enough, since bg_scroller could still
        # directly capture your scroll gestures instead of letting them
        # pass through to fg_scroller on top. This is what was causing
        # navigation to drive the background layer instead of the
        # foreground.
        self.bg_scroller.set_can_target(False)
        self.bg_scroller.set_vexpand(True)
        self.bg_scroller.set_hexpand(True)
        self.bg_scroller.set_valign(Gtk.Align.FILL)
        self.bg_scroller.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.bg_scroller.set_child(self.bg_view)
        self.bg_scroller.add_css_class("parallax-background")
        overlay.set_child(self.bg_scroller)

        # Foreground layer: sharp thumbnails, this is what the user scrolls
        self.fg_store = Gio.ListStore(item_type=_ParallaxItem)
        fg_factory = Gtk.SignalListItemFactory()
        fg_factory.connect("setup", self._on_fg_setup)
        fg_factory.connect("bind", self._on_fg_bind)
        fg_factory.connect("unbind", self._on_fg_unbind)
        self.selection = Gtk.SingleSelection(model=self.fg_store)
        self.selection.set_autoselect(False)
        self.selection.connect("selection-changed", self._on_selected)
        self.fg_view = Gtk.ListView(model=self.selection, factory=fg_factory)
        self.fg_view.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.fg_scroller = Gtk.ScrolledWindow()
        self.fg_scroller.add_css_class("hide-scrollbar")
        self.fg_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        # Force both scrollers to actually overlap over the same full
        # area, rather than each sizing to its own content's natural
        # height — without this, bg's taller (400px) items vs fg's
        # shorter (240px) items could size each scroller differently,
        # rendering as two separate stacked rows instead of a true
        # layered parallax effect.
        self.fg_scroller.set_vexpand(True)
        self.fg_scroller.set_hexpand(True)
        self.fg_scroller.set_valign(Gtk.Align.FILL)
        self.fg_scroller.set_child(self.fg_view)
        overlay.add_overlay(self.fg_scroller)

        fg_adjustment = self.fg_scroller.get_hadjustment()
        fg_adjustment.connect("value-changed", self._on_fg_scroll)

        # Explicit keyboard navigation, not GtkListView's built-in arrow
        # handling — trusting that default behavior on a different layout
        # (Infinite Ribbon) previously caused a full blank-window crash,
        # so it's not something to rely on here without verifying it
        # first, which isn't possible without a live GTK4 environment.
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.fg_view.add_controller(key_controller)
        self.fg_view.connect("realize", lambda w: w.grab_focus())

        def register_css(widget):
            display = widget.get_display()
            if display is None:
                return
            hide_scrollbars(self.fg_scroller)
            base = Gdk.RGBA()
            base.parse("#78aaff")
            result = widget.get_style_context().lookup_color("theme_selected_bg_color")
            if result[0]:
                base = result[1]
            ring = base.copy()
            ring.alpha = 0.55
            css = _CSS_TEMPLATE.replace(b"{ring}", ring.to_string().encode())
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        self.fg_scroller.connect("realize", register_css)
        return overlay

    def on_activate(self):
        self.fg_view.grab_focus()

    def _apply_wallpapers(self, paths: list[str]):
        bg_items = [_ParallaxItem(path) for path in paths]
        fg_items = [_ParallaxItem(path) for path in paths]
        self.bg_store.splice(0, self.bg_store.get_n_items(), bg_items)
        self.fg_store.splice(0, self.fg_store.get_n_items(), fg_items)
        self._n_items = len(paths)

        if paths:
            def focus_first(attempt=[0]):
                adjustment = self.fg_scroller.get_hadjustment()
                attempt[0] += 1
                if adjustment.get_upper() < FG_STRIDE and attempt[0] < 60:
                    return GLib.SOURCE_CONTINUE  # not measured enough yet — retry
                self._set_focus(0, announce=False)
                self.fg_view.grab_focus()
                return GLib.SOURCE_REMOVE

            GLib.idle_add(focus_first)

    def _on_bg_setup(self, factory, list_item):
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(320, 400)
        picture.set_opacity(0.35)  # dimmed, per spec's "background... fade"-style depth cue
        picture.set_halign(Gtk.Align.CENTER)
        picture.set_valign(Gtk.Align.CENTER)
        picture.set_hexpand(False)
        picture.set_vexpand(False)
        list_item.set_child(picture)

    def _on_bg_bind(self, factory, list_item):
        item: _ParallaxItem = list_item.get_item()
        picture: Gtk.Picture = list_item.get_child()
        picture.set_paintable(None)  # clear stale content while loading

        def on_ready(item_id, texture, picture=picture):
            picture.set_paintable(texture)

        # item_id doesn't need to be unique the way the carousel's
        # duplicated-path case required — bg_loader is a separate loader
        # instance from fg_loader, so path alone is a safe key here.
        self.bg_loader.request(item.path, item.path, on_ready)

    def _on_fg_setup(self, factory, list_item):
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(180, 240)
        picture.set_halign(Gtk.Align.CENTER)
        picture.set_valign(Gtk.Align.CENTER)
        picture.set_hexpand(False)
        picture.set_vexpand(False)
        picture.set_margin_start(6)
        picture.set_margin_end(6)
        picture.add_css_class("parallax-fg")
        list_item.set_child(picture)

    def _on_fg_bind(self, factory, list_item):
        item: _ParallaxItem = list_item.get_item()
        picture: Gtk.Picture = list_item.get_child()
        self._live_fg[item.path] = picture
        picture.set_paintable(None)

        # A recycled row must carry the same focus-ring state the row it
        # replaced had, or the ring flickers to the wrong card.
        focus_item = None
        if self._focus is not None:
            focus_item = self.fg_store.get_item(self._focus)
        if focus_item is not None and item.path == focus_item.path:
            picture.add_css_class("focused")
        else:
            picture.remove_css_class("focused")

        def on_ready(item_id, texture, picture=picture):
            picture.set_paintable(texture)

        self.fg_loader.request(item.path, item.path, on_ready)

    def _on_fg_unbind(self, factory, list_item):
        item: _ParallaxItem = list_item.get_item()
        if item is not None:
            self.fg_loader.cancel(item.path)
            self._live_fg.pop(item.path, None)
        picture: Gtk.Picture = list_item.get_child()
        picture.remove_css_class("focused")

    def _on_fg_scroll(self, adjustment):
        bg_adjustment = self.bg_scroller.get_hadjustment()
        bg_adjustment.set_value(adjustment.get_value() * PARALLAX_RATIO)

    def _on_selected(self, selection, position, n_items):
        item = self.selection.get_selected_item()
        if item is not None:
            self.emit("wallpaper-selected", item.path)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            if not getattr(self, "_n_items", 0):
                return True  # consume the key even if not ready yet
            if self._focus is None:
                self._focus = 0
            step = 1 if keyval == Gdk.KEY_Right else -1
            new_position = max(0, min(self._n_items - 1, self._focus + step))
            self._set_focus(new_position)
            return True  # fully consume — do not let GtkListView's own handling run too
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._focus is not None:
                # Only Enter (or a click) commits the selection, which is
                # what triggers the wallpaper-selected emission.
                self.selection.set_selected(self._focus)
            return True
        return False

    def _scroll_to_index(self, position: int):
        """Bring an item into view WITHOUT changing selection — visual
        focus only. Same Gtk.ListView.scroll_to() first / FG_STRIDE
        fallback pattern as before, but with the FOCUS flag alone: the
        SELECT flag is what turned arrow navigation into automatic
        wallpaper-selected emissions, so it's deliberately never used
        for keyboard movement. Only the foreground position is set
        directly here — the background follows automatically via
        _on_fg_scroll, which listens to the foreground adjustment's
        value-changed signal."""
        try:
            flags = Gtk.ListScrollFlags.FOCUS
            self.fg_view.scroll_to(position, flags, None)
            return
        except Exception:
            pass  # fall through to the manual method below

        adjustment = self.fg_scroller.get_hadjustment()
        target_value = position * FG_STRIDE
        viewport_width = self.fg_scroller.get_width()
        if viewport_width > 0:
            target_value -= (viewport_width - FG_STRIDE) / 2
        adjustment.set_value(max(0.0, target_value))

    def _apply_focus_to_live(self):
        focus_path = None
        if self._focus is not None:
            item = self.fg_store.get_item(self._focus)
            if item is not None:
                focus_path = item.path
        for path, picture in self._live_fg.items():
            if path == focus_path:
                picture.add_css_class("focused")
            else:
                picture.remove_css_class("focused")

    def _set_focus(self, position: int, announce: bool = True):
        if not getattr(self, "_n_items", 0):
            return
        position = max(0, min(self._n_items - 1, position))
        self._focus = position
        self._scroll_to_index(position)
        self._apply_focus_to_live()
        if announce:
            item = self.fg_store.get_item(position)
            say(f"Focus: {item.path}")
