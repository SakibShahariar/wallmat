"""
Layout #5: Infinite Ribbon (spec-ranked 3/8)

Same skewed carousel as Split-Screen, but the underlying Gio.ListStore
holds the wallpaper list duplicated 3x (spec's suggested approach), and
we silently snap the scroll position back into the middle copy whenever
the user scrolls into the first or last copy — giving the illusion of
an infinite loop without actually holding infinite items.

Left/Right arrow navigation is handled entirely by our own
Gtk.EventControllerKey, NOT GtkListView's built-in keyboard handling.
An earlier version relied on the ListView's default arrow behavior,
which produced a completely blank window after a single keypress —
its exact behavior for a horizontally-oriented ListView with a custom
selection/model setup like this one isn't something I could verify
without a live GTK4 environment, and evidently it did something
unexpected. Intercepting the keys ourselves (CAPTURE phase, consuming
the event) removes that uncertainty — every position/selection change
now goes through the same code path regardless of whether it was
triggered by keyboard, click, or scroll.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

from .base import WallLayout
from announce import say
from widgets.wallpaper_carousel import WallpaperCarousel, CARD_WIDTH
from widgets.skewed_card import natural_width

# CARD_WIDTH alone significantly undercounts the actual per-item scroll
# increment — two things were missing:
# 1. The 6px margins on both sides of each card (see wallpaper_carousel.py
#    _on_setup): +12px.
# 2. SkewedCard.do_measure() adds a "skew_pad" term on top of base_width
#    to accommodate the skew transform — with the exact base_width/
#    base_height/skew_deg the carousel actually constructs cards with
#    (130 / 169 / the default -12°), that's roughly another +35px, which
#    an earlier version of this file missed entirely. natural_width() is
#    imported directly from skewed_card.py so this stays exactly in sync
#    with the real do_measure() calculation rather than a second,
#    independently-guessed formula that can silently drift out of sync.
CARD_STRIDE = natural_width(CARD_WIDTH, int(CARD_WIDTH * 1.3)) + 12


class InfiniteRibbonLayout(WallLayout):
    display_name = "Infinite Ribbon"
    performance_tier = "fast"

    def __init__(self):
        super().__init__()
        # Keyboard navigation moves this (focus = "the card you'd select
        # with Enter"), NOT the Gtk.SingleSelection. Selection is only
        # committed on Enter (or a click) so arrows never emit
        # wallpaper-selected.
        self._focus = None

    def build(self) -> Gtk.Widget:
        self.carousel = WallpaperCarousel(fill_height=True)
        self.carousel.set_vexpand(True)
        self.carousel.set_hexpand(True)
        self.carousel.connect("wallpaper-selected", self._on_selected)

        adjustment = self.carousel.scroller.get_hadjustment()
        adjustment.connect("value-changed", self._on_scroll)

        # Intercept Left/Right ourselves, in CAPTURE phase so we see the
        # event before GtkListView's own (unverified, evidently broken
        # for our setup) built-in arrow handling gets a chance. Returning
        # True consumes the event, fully preventing that default handling
        # from also running.
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.carousel.list_view.add_controller(key_controller)

        self.carousel.list_view.connect("realize", lambda w: w.grab_focus())

        return self.carousel

    def on_activate(self):
        self.carousel.list_view.grab_focus()

    def _apply_wallpapers(self, paths: list[str]):
        if not paths:
            self.carousel.load_wallpapers([])
            return
        # Triplicate the list so there's always a "previous" and "next"
        # copy to scroll into before we need to snap back.
        self._single_set_len = len(paths)
        looped = paths * 3
        self.carousel.load_wallpapers(looped)

        # Start scrolled into the middle copy, with the first wallpaper
        # of that copy FOCUSED (not selected — keyboard focus moves
        # freely; selection is committed with Enter). A single idle_add
        # callback isn't reliably enough — Gtk.Adjustment.set_value()
        # clamps to whatever range it currently knows about, and if the
        # ListView hasn't finished measuring all its (virtualized) items
        # yet, the adjustment's range may still be too small to actually
        # contain the middle-copy position we're aiming for, silently
        # clamping our jump down to somewhere arbitrary. Retrying every
        # idle cycle until the range is big enough avoids that —
        # focus (a model-level operation, unaffected by adjustment
        # range) is set right away; only the visual scroll needed the
        # retry loop.
        def scroll_to_middle(attempt=[0]):
            adjustment = self.carousel.scroller.get_hadjustment()
            n = self._single_set_len
            needed_upper = (n + 1) * CARD_STRIDE
            attempt[0] += 1
            if adjustment.get_upper() < needed_upper and attempt[0] < 60:
                # ~1 second of retries at typical idle-cycle frequency —
                # a safety cap so a genuine measurement failure elsewhere
                # can't spin this forever; if we hit the cap, jump anyway
                # with whatever range is currently available rather than
                # give up silently.
                return GLib.SOURCE_CONTINUE
            self._set_focus(n, announce=False)
            self.carousel.list_view.grab_focus()
            return GLib.SOURCE_REMOVE

        GLib.idle_add(scroll_to_middle)

    def _scroll_to_index(self, position: int):
        """Bring a specific item into view WITHOUT touching selection —
        only the visual focus moves. Tries Gtk.ListView.scroll_to() with
        the FOCUS flag first (lets GTK compute the exact position from
        its own layout knowledge), falling back to the manual
        CARD_STRIDE-based estimate that has already been through several
        rounds of fixes. The SELECT flag is deliberately never passed
        here: keyboard nav moving the selection is what turned arrow
        presses into automatic wallpaper-selected emissions."""
        try:
            flags = Gtk.ListScrollFlags.FOCUS
            self.carousel.list_view.scroll_to(position, flags, None)
            return
        except Exception:
            pass  # fall through to the manual method below

        adjustment = self.carousel.scroller.get_hadjustment()
        target_value = position * CARD_STRIDE
        viewport_width = self.carousel.scroller.get_width()
        if viewport_width > 0:
            target_value -= (viewport_width - CARD_STRIDE) / 2
        adjustment.set_value(max(0.0, target_value))

    def _set_focus(self, position: int, announce: bool = True):
        """Move keyboard focus to `position` in the tripled list. Wraps
        (modulo 3n) exactly like _go_to_position did — including negative
        positions, so arrow-left from the middle copy never lands on an
        invalid index."""
        n = self._single_set_len
        if not n:
            return
        position = position % (3 * n)
        self._focus = position
        self._scroll_to_index(position)
        if self.carousel.store.get_n_items() > position:
            self.carousel.set_focus(self.carousel.store.get_item(position).item_id)
        if announce:
            item = self.carousel.store.get_item(position)
            say(f"Focus: {item.path}")

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            if not getattr(self, "_single_set_len", 0):
                return True  # consume the key even if not ready yet
            if self._focus is None:
                self._focus = self._single_set_len  # start at the middle copy
            step = 1 if keyval == Gdk.KEY_Right else -1
            self._set_focus(self._focus + step)
            return True  # fully consume — do not let GtkListView's own handling run too
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._focus is not None:
                # Committing the focused card is the ONLY keyboard path
                # that changes selection — which is what triggers the
                # wallpaper-selected emission (and its "Selected:" print).
                self.carousel.selection.set_selected(self._focus)
            return True
        return False

    def _on_scroll(self, adjustment):
        if not getattr(self, "_single_set_len", 0):
            return
        set_span = self._single_set_len * CARD_STRIDE
        value = adjustment.get_value()

        # Loop illusion: snap the scroll position back into the middle
        # copy when the user scrolls into the first or last one. Only the
        # scroll position moves here — selection and focus stay exactly
        # where the user put them, so mouse-scroll never emits
        # wallpaper-selected.
        if value < set_span * 0.5:
            adjustment.set_value(value + set_span)
        elif value > set_span * 1.5:
            adjustment.set_value(value - set_span)

    def _on_selected(self, carousel, path):
        self.emit("wallpaper-selected", path)
