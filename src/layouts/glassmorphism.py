"""
Layout #4: Glassmorphism Carousel (spec-ranked 5/8)

Reuses the same ListView/ListStore carousel structure as the skewed
carousel, but instead of the skew transform each cell gets CSS opacity
dimming + a glow-ring on the active (selected) item. True frosted-glass
blur (spec section: "needs Gtk.DrawingArea / Cairo for real backdrop
blur") is NOT implemented here — this uses translucent color panels as a
cheap approximation, matching the spec's own "Medium — CSS opacity +
rgba() works" feasibility note.

The active-item glow IS wired up: `.glass-card.active` is applied to the
currently-selected row (and removed from every other live row) from the
selection-changed handler, and re-applied on bind/unbind as ListView
recycles rows. Keyboard ←/→ and clicking a card both move the glow.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GObject, Gdk, Adw

from .base import WallLayout
from announce import say
from widgets.thumbnail_loader import ThumbnailLoader
from widgets.accessibility import wallpaper_accessible_name
from widgets.gsk_utils import (
    hide_scrollbars, register_css_once, enable_vertical_wheel_scroll,
)

_GLASS_STRIDE = 180 + 12  # per-item scroll increment (180 card + 6px margins each side)

_HIGH_CONTRAST_CSS = b"""
.wallmat-glass.high-contrast .glass-card {
    opacity: 1.0;
    background-color: {background};
    border: 2px solid {foreground};
}
.wallmat-glass.high-contrast .glass-card.active,
.wallmat-glass.high-contrast .glass-card.hovered {
    border: 3px solid {selected};
    box-shadow: none;
}
.wallmat-glass.high-contrast listitem:focus .glass-card,
.wallmat-glass.high-contrast .glass-card:focus {
    outline: 3px solid {foreground};
    outline-offset: 2px;
    box-shadow: none;
}
.wallmat-glass.high-contrast listitem:focus .glass-card.active {
    outline: 3px solid {foreground};
    border: 3px solid {selected};
    box-shadow: none;
}
"""

_CSS_TEMPLATE = b"""
/* The theme draws a focus outline on the focused ListView row itself.
   Rows fill the scroller height, so that outline appears as a tall
   rectangle around the row, on top of our card-border ring. Our
   .glass-card.focused ring is the intended focus indicator. GTK 4.24
   names this CSS node "row"; older releases used "listitem", so cover
   both. High-contrast keeps its explicit outline on .glass-card itself,
   which is a different node and is not affected by this rule. */
.wallmat-glass row,
.wallmat-glass row:focus,
.wallmat-glass row:hover,
.wallmat-glass row:selected,
.wallmat-glass row:active,
.wallmat-glass listitem,
.wallmat-glass listitem:focus,
.wallmat-glass listitem:hover,
.wallmat-glass listitem:selected,
.wallmat-glass listitem:active {
    outline: none;
    box-shadow: none;
    background: none;
    background-image: none;
    border: none;
}

.glass-card {
    background-color: rgba(255,255,255,0.06);
    border-radius: 16px;
    opacity: 0.5;
    transition: opacity 200ms ease;
}
.glass-card.active {
    opacity: 1.0;
    box-shadow: 0 0 24px 4px {glow};
}
/* The focus ring is drawn on the card itself, so it can never drift out
   of alignment with the wallpaper. The tall GTK row focus outline is
   suppressed above (row:focus), leaving exactly one ring. */
.glass-card.focused {
    opacity: 1.0;
    box-shadow: 0 0 0 3px {ring};
}
.glass-card.active.focused {
    opacity: 1.0;
    box-shadow: 0 0 24px 4px {glow}, 0 0 0 3px {ring};
}

.glass-card.hovered {
    background-color: rgba(255,255,255,0.12);
}
.glass-card picture {
    border-radius: 16px;
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


class _GlassItem(GObject.Object):
    path = GObject.Property(type=str)

    def __init__(self, path):
        super().__init__()
        self.path = path


class GlassmorphismLayout(WallLayout):
    display_name = "Glassmorphism"
    performance_tier = "medium"

    def _sync_high_contrast_class(self, widget, style_manager):
        getter = getattr(style_manager, "get_high_contrast", None)
        enabled = bool(getter()) if getter is not None else False
        if enabled:
            widget.add_css_class("high-contrast")
        else:
            widget.remove_css_class("high-contrast")

    def __init__(self):
        super().__init__()
        # Keyboard navigation moves focus only; selection (glow +
        # wallpaper-selected emission) happens exclusively on Enter or a
        # click.
        self._focus = None

    def build(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.set_vexpand(True)
        outer.set_hexpand(True)
        outer.add_css_class("wallmat-glass")
        self._outer = outer

        self.loader = ThumbnailLoader(thumb_size=480)  # cards render at 180x240
        self._live_widgets: dict[str, Gtk.Picture] = {}  # path -> currently-bound picture
        self.store = Gio.ListStore(item_type=_GlassItem)
        self.selection = Gtk.SingleSelection(model=self.store)
        self.selection.set_autoselect(False)
        self.selection.connect("selection-changed", self._on_selection_changed)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind)
        factory.connect("unbind", self._on_unbind)

        self.list_view = Gtk.ListView(model=self.selection, factory=factory)
        self.list_view.set_orientation(Gtk.Orientation.HORIZONTAL)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.add_css_class("hide-scrollbar")
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.scroller.set_vexpand(True)
        self.scroller.set_hexpand(True)
        self.scroller.set_child(self.list_view)

        # Explicit keyboard navigation, not GtkListView's built-in arrow
        # handling — same reasoning as infinite_ribbon.py / parallax_
        # gallery.py: trusting the default behavior with a horizontal,
        # custom-selection setup produced a blank window before.
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.list_view.add_controller(key_controller)
        self.list_view.connect("realize", lambda w: w.grab_focus())
        # Keep the focused (and therefore centred) card in sync with
        # mouse-wheel/trackpad scrolling.
        self.scroller.get_hadjustment().connect("value-changed", self._on_scroll)

        # Register the CSS provider once a real Gdk.Display is available
        # (i.e. once this widget is attached to a realized window), rather
        # than trying to fetch a display before one exists. The ring/glow
        # colors are resolved at runtime from the theme's named color
        # theme_selected_bg_color and inlined as rgba — using @name in the
        # stylesheet directly would NOT resolve, because @define-color
        # names only live inside the provider that declares them (the
        # user's theme gtk.css), not across providers.
        def register_css(widget):
            display = widget.get_display()
            if display is None:
                return
            hide_scrollbars(self.scroller)
            base = Gdk.RGBA()
            base.parse("#78aaff")
            result = widget.get_style_context().lookup_color("theme_selected_bg_color")
            if result[0]:
                base = result[1]
            ring = base.copy()
            ring.alpha = 0.55
            glow = base.copy()
            glow.alpha = 0.6
            css = _CSS_TEMPLATE.replace(b"{ring}", ring.to_string().encode())
            css = css.replace(b"{glow}", glow.to_string().encode())
            register_css_once(
                "glassmorphism", display, css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            def theme_color(name, fallback):
                found, color = widget.get_style_context().lookup_color(name)
                return color.to_string().encode() if found else fallback

            high_contrast_css = _HIGH_CONTRAST_CSS
            high_contrast_css = high_contrast_css.replace(
                b"{background}", theme_color("theme_bg_color", b"#000000")
            )
            high_contrast_css = high_contrast_css.replace(
                b"{foreground}", theme_color("theme_fg_color", b"#ffffff")
            )
            high_contrast_css = high_contrast_css.replace(
                b"{selected}", theme_color("theme_selected_bg_color", b"#ffffff")
            )
            register_css_once(
                "glassmorphism-high-contrast", display, high_contrast_css,
                Gtk.STYLE_PROVIDER_PRIORITY_USER,
            )

            style_manager = Adw.StyleManager.get_default()
            self._sync_high_contrast_class(outer, style_manager)
            if hasattr(style_manager, "get_high_contrast"):
                try:
                    style_manager.connect(
                        "notify::high-contrast",
                        lambda manager, _pspec: self._sync_high_contrast_class(
                            outer, manager
                        ),
                    )
                except TypeError:
                    pass

        self.scroller.connect("realize", register_css)
        enable_vertical_wheel_scroll(self.scroller)

        outer.append(self.scroller)

        hint = Gtk.Label(label="← / → to browse, Enter or click to select")
        hint.add_css_class("dim-label")
        hint.set_margin_bottom(6)
        outer.append(hint)

        return outer

    def on_activate(self):
        self.list_view.grab_focus()

    def _apply_focus_to_live(self):
        """Push the current keyboard-focus ring to the live rows."""
        focus_path = None
        if self._focus is not None:
            item = self.store.get_item(self._focus)
            if item is not None:
                focus_path = item.path
        for path, picture in self._live_widgets.items():
            if path == focus_path:
                picture.add_css_class("focused")
            else:
                picture.remove_css_class("focused")

    def _apply_wallpapers(self, paths: list[str]):
        items = [_GlassItem(path) for path in paths]
        self.store.splice(0, self.store.get_n_items(), items)
        if paths:
            self._set_focus(0, announce=False)

    def _on_setup(self, factory, list_item):
        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(180, 240)
        # Same fix as the main carousel: without explicit alignment,
        # ListView stretches each Picture to fill the full row height
        # instead of respecting the 180x240 size request.
        picture.set_halign(Gtk.Align.CENTER)
        picture.set_valign(Gtk.Align.CENTER)
        picture.set_hexpand(False)
        picture.set_vexpand(False)
        picture.set_margin_start(6)
        picture.set_margin_end(6)
        picture.add_css_class("glass-card")
        picture.set_cursor_from_name("pointer")
        # Hover feedback: the row's default GTK hover highlight is
        # suppressed by _CSS above (it clashed with the glow/opacity
        # visuals), so without this, cards give zero visual response to
        # hovering before a click.
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda c, x, y, p=picture: p.add_css_class("hovered"))
        motion.connect("leave", lambda c, p=picture: p.remove_css_class("hovered"))
        picture.add_controller(motion)
        list_item.set_child(picture)

    def _on_bind(self, factory, list_item):
        item: _GlassItem = list_item.get_item()
        picture: Gtk.Picture = list_item.get_child()

        self._live_widgets[item.path] = picture

        # A recycled row must carry the same glow state the row it replaced
        # had, or the selection border flickers to the wrong card while the
        # selection itself stays put.
        selected_item = self.selection.get_selected_item()
        is_selected = selected_item is item
        picture.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [wallpaper_accessible_name(item.path), "Selected" if is_selected else "Wallpaper thumbnail"],
        )
        picture.add_css_class("active") if is_selected else picture.remove_css_class("active")

        def on_ready(item_id, texture, picture=picture):
            # ListView rows are recycled; never paint into a row that has
            # since been rebound or unbound.
            if self._live_widgets.get(item_id) is picture:
                picture.set_paintable(texture)

        self.loader.request(item.path, item.path, on_ready)

    def _on_unbind(self, factory, list_item):
        item: _GlassItem = list_item.get_item()
        if item is not None:
            self.loader.cancel(item.path)
            self._live_widgets.pop(item.path, None)
        picture: Gtk.Picture = list_item.get_child()
        picture.set_paintable(None)
        picture.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            ["Wallpaper thumbnail", "Recycled wallpaper image"],
        )
        picture.remove_css_class("active")
        picture.remove_css_class("focused")
        picture.remove_css_class("hovered")

    def _on_selection_changed(self, selection, position, n_items):
        item = self.selection.get_selected_item()
        # Toggle the glow on every currently-live row, not just the newly
        # selected one — the previously-selected row (if still bound/visible)
        # needs its glow cleared too.
        for path, picture in self._live_widgets.items():
            is_selected = item is not None and item.path == path
            picture.update_property(
                [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
                [wallpaper_accessible_name(path), "Selected" if is_selected else "Wallpaper thumbnail"],
            )
            if is_selected:
                picture.add_css_class("active")
            else:
                picture.remove_css_class("active")
        if item is not None:
            self.emit("wallpaper-selected", item.path)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            n = self.store.get_n_items()
            if n == 0:
                return True  # consume the key even if not ready yet
            if self._focus is None:
                self._focus = 0
            step = 1 if keyval == Gdk.KEY_Right else -1
            self._set_focus(max(0, min(n - 1, self._focus + step)))
            return True  # fully consume — do not let GtkListView's own handling run too
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._focus is not None:
                # Only Enter (or a click) commits selection — which is
                # what triggers the glow movement + wallpaper-selected.
                self.selection.set_selected(self._focus)
            return True
        return False

    def _stride(self) -> float:
        """Actual per-row width, from GtkListView's own measurement.

        The 192px estimate (180px card + 12px margins) was wrong: GTK adds
        row spacing, so the error grew with the index and the frame drifted
        further off the focused card the deeper you scrolled.
        """
        n = self.store.get_n_items()
        if n < 1:
            return _GLASS_STRIDE
        adjustment = self.scroller.get_hadjustment()
        if adjustment.get_upper() > 0:
            return adjustment.get_upper() / n
        return _GLASS_STRIDE

    def _scroll_to_index(self, position: int):
        """Centre an item under the static frame WITHOUT changing selection.
        GtkListView.scroll_to() only guarantees visibility, not centering.
        """
        adjustment = self.scroller.get_hadjustment()
        stride = self._stride()
        viewport_width = self.scroller.get_width()
        target = position * stride + stride / 2.0 + 6.0 - viewport_width / 2.0
        adjustment.set_value(max(0.0, target))

    def _on_scroll(self, adjustment):
        n = self.store.get_n_items()
        viewport_width = self.scroller.get_width()
        if n < 1 or viewport_width <= 0:
            return
        stride = self._stride()
        center = adjustment.get_value() + viewport_width / 2.0
        position = round((center - stride / 2.0 - 6.0) / stride)
        position = max(0, min(n - 1, position))
        if position != self._focus:
            # No scroll-back: that would feed into value-changed again.
            self._set_focus(position, announce=False, scroll=False)

    def _set_focus(self, position: int, announce: bool = True, scroll: bool = True):
        n = self.store.get_n_items()
        if n == 0:
            return
        position = max(0, min(n - 1, position))
        self._focus = position
        if scroll:
            self._scroll_to_index(position)
        self._apply_focus_to_live()
        if announce:
            item = self.store.get_item(position)
            say(f"Focus: {item.path}")