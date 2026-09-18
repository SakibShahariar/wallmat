"""
Layout #2: Stacked Deck Selector (spec-ranked fastest: 1/8)

Three physical cards, each with ONE rotation fixed forever at
construction (0°, -4°, +4° — never touched again for the lifetime of
that card). Rotation belongs to the CARD, not to a spatial "front/mid/
back" role. What changes over time is which card currently plays the
front (interactable) role, tracked via a mutable paint-order list.

This is drawn by a single custom Gtk.Widget managing all 3 cards
directly, rather than 3 separate widgets inside a Gtk.Overlay — Gtk.
Overlay has no public API to reorder its children's paint order after
construction, and dynamic z-order is exactly what this layout needs
(which physical card is "on top" changes every deal). Drawing all 3
layers ourselves in one do_snapshot, in whatever order a Python list
says, is the only way to get that.

Promoting a card to front requires NO animation — it was already
sitting exactly where it is, at its own fixed rotation, the whole time.
Only the departing front card animates (slides away), then gets
recycled to the back of the order with fresh content once fully
invisible, keeping its own original rotation unchanged. Because
rotation travels with the card rather than the position, the angle you
see at "front" cycles 0 -> -4 -> +4 -> 0 -> ... as successive deals
promote a different physical card, while content simultaneously
progresses through the collection (a b c -> b c d -> c d e).

Images route through ThumbnailLoader (async, downscaled, disk-cached,
fixed worker pool) — an earlier version decoded synchronously on the
main thread via GdkPixbuf on every card load AND every deal/swipe, the
exact anti-pattern parallax_gallery.py's docstring documents fixing
elsewhere in this app (uncached, main-thread-blocking decode). This was
the one layout still doing that; it now matches the rest of the app.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gtk, Gdk, Graphene, Gsk, GLib

from .base import WallLayout
from announce import say
from widgets.gsk_utils import draw_texture_cover, get_focus_ring_rgba, draw_focus_ring, get_animations_enabled
from widgets.thumbnail_loader import ThumbnailLoader

CARD_ROTATIONS_DEG = [0.0, -4.0, 4.0]  # fixed per card, forever
CARD_WIDTH = 560
CARD_HEIGHT = 340

DEAL_ANIMATION_MS = 220
DEAL_SLIDE_DISTANCE = CARD_WIDTH * 1.3
RISE_ANIMATION_MS = 200


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class _DeckSlot:
    """One physical card. rotation is set once and never reassigned by
    any code in this file after construction."""

    def __init__(self, rotation: float):
        self.rotation = rotation
        self.texture: Gdk.Texture | None = None
        # The path this slot's texture request is FOR, set the moment a
        # request is issued. An async decode's on_ready callback only
        # applies its result if this still matches — guards against a
        # slow-loading request from an earlier deal landing on a slot
        # that's since moved on to a different image.
        self.pending_path: str | None = None
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.scale = 1.0
        self.opacity = 1.0


class _DeckWidget(Gtk.Widget):
    """Draws 3 _DeckSlot cards in an explicit, mutable paint order — the
    only way to get dynamic z-order, since Gtk.Overlay can't reorder its
    children after construction."""

    __gtype_name__ = "DeckWidget"

    def __init__(self):
        super().__init__()
        self.slots = [_DeckSlot(r) for r in CARD_ROTATIONS_DEG]
        # paint order: index 0 = back (painted first, least visible),
        # index -1 = front (painted last, topmost/interactable).
        # paint_order[-1] is front, [0] is back. Must start reversed
        # relative to construction order so front begins at slot0 (0°),
        # matching the initial "0 -4 4" state — otherwise paint_order[-1]
        # would start as slot2 (+4°) instead.
        self.paint_order: list[_DeckSlot] = list(reversed(self.slots))
        self.set_size_request(CARD_WIDTH, CARD_HEIGHT)

        # Purely visual hover cue (brightens the front/clickable card) —
        # there's otherwise no affordance telling the user this hand-drawn
        # widget is clickable before they click it.
        self._hovered = False
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda c, x, y: self._set_hovered(True))
        motion.connect("leave", lambda c: self._set_hovered(False))
        self.add_controller(motion)
        self.set_cursor_from_name("pointer")

    def _set_hovered(self, value: bool):
        if value != self._hovered:
            self._hovered = value
            self.queue_draw()

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return CARD_WIDTH, CARD_WIDTH, -1, -1
        return CARD_HEIGHT, CARD_HEIGHT, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return

        for slot in self.paint_order:
            if slot.opacity <= 0.0:
                continue

            center = Graphene.Point().init(width / 2.0, height / 2.0)
            transform = Gsk.Transform.new()
            transform = transform.translate(Graphene.Point().init(slot.offset_x, slot.offset_y))
            transform = transform.translate(center)
            transform = transform.rotate(slot.rotation)  # this card's own fixed value, always
            transform = transform.scale(slot.scale, slot.scale)
            transform = transform.translate(Graphene.Point().init(-width / 2.0, -height / 2.0))

            snapshot.save()
            snapshot.transform(transform)

            if slot.opacity < 1.0:
                snapshot.push_opacity(slot.opacity)

            rect = Graphene.Rect().init(0, 0, width, height)
            frame_color = Gdk.RGBA()
            frame_color.parse("#2e2e2e")
            snapshot.append_color(frame_color, rect)

            if slot.texture is not None:
                draw_texture_cover(snapshot, slot.texture, 0, 0, width, height)

            is_front = slot is self.paint_order[-1]

            # Hover highlight on the front (clickable) card only.
            if is_front and self._hovered:
                hover_overlay = Gdk.RGBA()
                hover_overlay.parse("rgba(255,255,255,0.10)")
                snapshot.append_color(hover_overlay, rect)

            # Keyboard focus ring on the topmost card: on the card edge,
            # matching the selection-border placement (an earlier version
            # inset the ring into the image); focus is told apart from a
            # committed selection by a thinner, semi-transparent stroke.
            # draw_focus_ring adds a dark backing stroke so the ring stays
            # legible over light/busy wallpaper content.
            if is_front:
                ring_color = get_focus_ring_rgba(self.get_style_context())
                ring_rect = Gsk.RoundedRect()
                ring_rect.init_from_rect(
                    Graphene.Rect().init(0, 0, width, height), 0
                )
                draw_focus_ring(snapshot, ring_rect, ring_color, ring_width=2.0)

            if slot.opacity < 1.0:
                snapshot.pop()

            snapshot.restore()


class StackedDeckLayout(WallLayout):
    display_name = "Stacked Deck"
    performance_tier = "fast"

    def __init__(self):
        super().__init__()
        self._deck_index = 0
        self._animating = False
        self._loader = ThumbnailLoader(thumb_size=640)  # card renders at 560x340
        # One-shot read of the reduced-motion preference — deal/rise
        # animations are skipped (jump straight to the end state) when the
        # user has animations disabled at the system level. Previously
        # this layout ran its slide/rise tweens unconditionally, unlike
        # the carousel-based layouts.
        self._animations_enabled = get_animations_enabled()

    def build(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_halign(Gtk.Align.CENTER)

        self.deck = _DeckWidget()
        self.deck.set_halign(Gtk.Align.CENTER)
        self.deck.set_valign(Gtk.Align.CENTER)
        self.deck.set_margin_top(20)
        self.deck.set_margin_bottom(20)
        self.deck.set_margin_start(20)
        self.deck.set_margin_end(20)

        swipe = Gtk.GestureSwipe.new()
        swipe.connect("swipe", self._on_swipe)
        self.deck.add_controller(swipe)

        click = Gtk.GestureClick.new()
        click.connect("released", lambda g, n, x, y: self._deal(1))
        self.deck.add_controller(click)

        outer.append(self.deck)

        hint = Gtk.Label(label="Swipe, click, or press ← / → to browse")
        hint.add_css_class("dim-label")
        outer.append(hint)

        select_button = Gtk.Button(label="Use this wallpaper")
        select_button.add_css_class("suggested-action")
        select_button.set_halign(Gtk.Align.CENTER)
        select_button.connect("clicked", lambda b: self._select_current())
        outer.append(select_button)

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        outer.add_controller(key_controller)

        self.deck.connect("realize", lambda w: self._load_all_cards())

        return outer

    def _apply_wallpapers(self, paths: list[str]):
        self._deck_index = 0
        self._load_all_cards()

    def _request_texture(self, slot: _DeckSlot, path: str):
        """Async, cached decode via the shared ThumbnailLoader — replaces
        the old synchronous, uncached GdkPixbuf.new_from_file_at_scale()
        call that ran on the main thread for every card load and every
        deal."""
        slot.pending_path = path

        def on_ready(item_id, texture, slot=slot, path=path):
            # Guard against a slow decode from an earlier deal landing on
            # a slot that's since been recycled to show something else.
            if slot.pending_path != path:
                return
            slot.texture = texture
            self.deck.queue_draw()

        self._loader.request(path, path, on_ready)

    def _load_all_cards(self):
        if not self._paths:
            return
        n = len(self._paths)
        # paint_order[-1] is front (deck_index+0), [-2] mid (+1), [0] back (+2).
        for i, slot in enumerate(reversed(self.deck.paint_order)):
            slot.texture = None  # clear any stale image while the new one decodes
            slot.offset_x = 0.0
            slot.offset_y = 0.0
            slot.scale = 1.0
            slot.opacity = 1.0
            self._request_texture(slot, self._paths[(self._deck_index + i) % n])
        self.deck.queue_draw()

    def _on_swipe(self, gesture, vx, vy):
        if not self._paths:
            return
        if abs(vx) > 50:
            self._deal(1 if vx < 0 else -1)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            if not self._paths or self._animating:
                return True
            step = 1 if keyval == Gdk.KEY_Right else -1
            self._deal(step)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._select_current()
            return True
        return False

    def _print_focus(self):
        """Called once a deal animation lands the new front card — the
        deck's keyboard 'focus' has no selection of its own, so arrows
        print Focus and only Enter/click actually selects."""
        if not self._paths:
            return
        path = self._paths[self._deck_index % len(self._paths)]
        say(f"Focus: {path}")

    def _deal(self, direction: int):
        if not self._paths or self._animating:
            return
        self._animating = True
        if direction > 0:
            self._deal_next()
        else:
            self._deal_previous()

    def _deal_next(self):
        deck = self.deck
        front = deck.paint_order[-1]

        if not self._animations_enabled:
            self._finish_deal_next(front)
            return

        start_time = GLib.get_monotonic_time()
        duration_us = DEAL_ANIMATION_MS * 1000
        target_offset = -DEAL_SLIDE_DISTANCE

        def step_out(_=None):
            elapsed = GLib.get_monotonic_time() - start_time
            t = min(1.0, elapsed / duration_us)
            eased = _ease_out_cubic(t)
            # Position/opacity only — this card's own rotation never changes.
            front.offset_x = target_offset * eased
            front.opacity = 1.0 - eased
            deck.queue_draw()

            if t >= 1.0:
                self._finish_deal_next(front)
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(16, step_out)

    def _finish_deal_next(self, front: _DeckSlot):
        """Recycle: front becomes the new back, keeping its own rotation
        exactly as it was — never reassigned. Shared by the animated and
        reduced-motion (instant) paths."""
        n = len(self._paths)
        self._deck_index = (self._deck_index + 1) % n
        front.texture = None
        self._request_texture(front, self._paths[(self._deck_index + 2) % n])
        front.offset_x = 0.0
        front.offset_y = 0.0
        front.scale = 1.0
        front.opacity = 1.0

        self.deck.paint_order.pop()             # remove front from the top
        self.deck.paint_order.insert(0, front)  # place it at the bottom
        self.deck.queue_draw()

        self._print_focus()

        # New front (previously mid) needs no animation — it was already
        # at rest, at its own fixed rotation, the whole time.
        self._animating = False

    def _deal_previous(self):
        deck = self.deck
        back = deck.paint_order[0]
        n = len(self._paths)
        self._deck_index = (self._deck_index - 1) % n
        back.texture = None
        self._request_texture(back, self._paths[self._deck_index % n])

        deck.paint_order.pop(0)      # remove back from the bottom
        deck.paint_order.append(back)  # place it at the top (front)
        deck.queue_draw()

        if not self._animations_enabled:
            back.offset_y = 0.0
            back.scale = 1.0
            back.opacity = 1.0
            deck.queue_draw()
            self._print_focus()
            self._animating = False
            return

        self._rise_in(back)

    def _rise_in(self, slot: _DeckSlot):
        """Position/scale/opacity only — rotation is this card's own
        fixed value throughout, never touched. Only called when
        animations are enabled; the reduced-motion path in
        _deal_previous() sets the end state directly instead."""
        duration_us = RISE_ANIMATION_MS * 1000
        start_offset_y = CARD_HEIGHT * 0.35
        start_scale = 0.85

        slot.offset_y = start_offset_y
        slot.scale = start_scale
        slot.opacity = 0.0

        start_time = GLib.get_monotonic_time()

        def step_in(_=None):
            elapsed = GLib.get_monotonic_time() - start_time
            t = min(1.0, elapsed / duration_us)
            eased = _ease_out_cubic(t)
            slot.offset_y = start_offset_y * (1.0 - eased)
            slot.scale = start_scale + (1.0 - start_scale) * eased
            slot.opacity = eased
            self.deck.queue_draw()

            if t >= 1.0:
                slot.offset_y = 0.0
                slot.scale = 1.0
                slot.opacity = 1.0
                self.deck.queue_draw()
                self._print_focus()
                self._animating = False
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(16, step_in)

    def _select_current(self):
        if not self._paths:
            return
        path = self._paths[self._deck_index % len(self._paths)]
        self.emit("wallpaper-selected", path)
