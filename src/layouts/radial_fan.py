"""
Layout #8: Radial Fan-Out Selector (spec-ranked 7/8, "Hard" feasibility)

Cards fan out from a center pivot point like a hand of cards, using polar
coordinates: each card's position and rotation are a function of its
angular offset from the "front" (top, angle=0) card.

Completed prototype (previous version deferred to Rust):

- Fully virtualized: this is a single custom Gtk.Widget that paints only
  the cards whose fanned rect intersects the viewport, instead of creating
  one Gtk.Fixed child per wallpaper. N wallpapers in a folder now cost at
  most ~8 painted cards per frame regardless of folder size — the old
  40-second launch freeze on ~47 images came from N synchronous main-thread
  decodes + N widgets; both are gone (async via ThumbnailLoader + draw-only-
  visible painting).
- Re-flows on resize: positions are recomputed every snapshot from the
  widget's live width/height, so the fan re-centers and rescales instead
  of pegging to a hardcoded point as Gtk.Fixed did.
- Back-to-front paint order via a mutable list, like stacked_deck.py's
  deck — the front (top) card always paints last so it's the readable one;
  the rest peek out behind it in a partial hand.
- Interaction: ←/→ or mouse/touchpad scroll cycles which card is "front";
  clicking a card selects and emits wallpaper-selected.

Images route through ThumbnailLoader (async, downscaled, cached).
"""

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gtk, Gdk, Graphene, Gsk

from .base import WallLayout
from announce import say
from widgets.thumbnail_loader import ThumbnailLoader
from widgets.gsk_utils import draw_card

CARD_WIDTH = 120
CARD_HEIGHT = 160
MAX_FAN_ANGLE_DEG = 60  # total arc span across all cards
PIVOT_BOTTOM_MARGIN = 44


def _signed_rel(n: int, front: int, target: int) -> int:
    """Signed card offset from `front` around the ring, shortest way round."""
    rel = (target - front) % n
    if rel > n // 2:
        rel -= n
    return rel


class _FanWidget(Gtk.Widget):
    __gtype_name__ = "FanWidget"

    def __init__(self):
        super().__init__()
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_size_request(560, 380)

        self._paths: list[str] = []
        self._textures: dict[str, Gdk.Texture] = {}
        self._loader = ThumbnailLoader(thumb_size=320)  # cards render at 120x160
        self._front = 0
        self._selection = 0  # path index last explicitly selected
        self._hovered = False

        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.HORIZONTAL
        )
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

        click = Gtk.GestureClick.new()
        click.connect("released", self._on_click)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda c, x, y: self._set_hovered(True))
        motion.connect("leave", lambda c: self._set_hovered(False))
        self.add_controller(motion)

        # Click-anywhere-in-the-fan selects the nearest card — a pointer
        # cursor signals that up front, since this hand-drawn widget has
        # no other affordance telling the user the fan is clickable.
        self.set_cursor_from_name("pointer")

        self.connect("realize", lambda w: w.grab_focus())

    def _set_hovered(self, value: bool):
        if value != self._hovered:
            self._hovered = value
            self.queue_draw()

    def set_paths(self, paths: list[str]):
        self._paths = list(paths)
        self._textures.clear()
        self._front = 0
        self._selection = 0
        for path in paths:
            def on_ready(item_id, texture, path=path):
                self._textures[item_id] = texture
                self.queue_draw()

            self._loader.request(path, path, on_ready)
        self.queue_draw()

    def _cycle_front(self, delta: int, announce: bool = False):
        """Move which card is top-of-fan (keyboard focus). Selection is
        NOT touched — commit with _commit_selection() (Enter / click)."""
        if not self._paths:
            return
        self._front = (self._front + delta) % len(self._paths)
        self.queue_draw()
        if announce:
            say(f"Focus: {self._paths[self._front]}")

    def _commit_selection(self):
        """Commit the current front card as the selection — the only path
        that triggers wallpaper-selected (and its "Selected:" print)."""
        if not self._paths:
            return
        self._selection = self._front
        self.emit_selection()

    def _geometry(self):
        """Returns (pivot_x, pivot_y, radius, angle_step, start_angle)."""
        width = self.get_width()
        height = self.get_height()
        pivot_x = width / 2.0
        pivot_y = height - PIVOT_BOTTOM_MARGIN
        radius = min(width * 0.55, height - PIVOT_BOTTOM_MARGIN - 24)
        n = len(self._paths)
        step = math.radians(MAX_FAN_ANGLE_DEG / max(1, n - 1)) if n > 1 else 0.0
        start_angle = math.radians(-MAX_FAN_ANGLE_DEG / 2)
        return pivot_x, pivot_y, radius, step, start_angle

    def _card_rect(self, pivot_x, pivot_y, radius, start_angle, step, rel: int):
        """Bottom-center of the card sits on the arc; card rotated about
        that point. Returns (bottom_x, bottom_y, angle_rad)."""
        angle = start_angle + rel * step
        bx = pivot_x + radius * math.sin(angle)
        by = pivot_y - radius * math.cos(angle)
        return bx, by, angle

    def _on_scroll(self, controller, dx, dy):
        delta = dy if dy != 0 else dx
        if delta != 0 and len(self._paths) > 1:
            self._cycle_front(1 if delta < 0 else -1)
        return True

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            if not self._paths:
                return True
            step = 1 if keyval == Gdk.KEY_Right else -1
            self._cycle_front(step, announce=True)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._commit_selection()
            return True
        return False

    def _on_click(self, gesture, n_press, x, y):
        if not self._paths:
            return
        pivot_x, pivot_y, radius, step, start_angle = self._geometry()
        # Find the card whose fanned rect contains the click. Most cards
        # overlap; the topmost (smallest |rel|) match wins — walk the SAME
        # order do_snapshot paints in (outermost first, front/rel=0 last)
        # and remember the last hit. Iterating in plain ascending `rel`
        # order here (instead of this paint order) was a real bug: on a
        # tie in |rel| (e.g. rel=-2 and rel=+2), "last one wins" picked
        # whichever had the larger rel, not whichever was actually drawn
        # on top — so a click in an overlap zone could select a card
        # other than the one visibly under the cursor.
        hit = None
        n = len(self._paths)
        rels = sorted(range(-(n // 2), n - (n // 2)), key=lambda r: -abs(r))
        for rel in rels:
            idx = (self._front + rel) % n
            bx, by, angle = self._card_rect(pivot_x, pivot_y, radius, start_angle, step, rel)
            # Point in unrotated card space (card drawn at -w/2..w/2, -h..0)
            cos_a, sin_a = math.cos(-angle), math.sin(-angle)
            rx, ry = x - bx, y - by
            local_x = rx * cos_a - ry * sin_a
            local_y = rx * sin_a + ry * cos_a
            if -CARD_WIDTH / 2 <= local_x <= CARD_WIDTH / 2 and -CARD_HEIGHT <= local_y <= 0:
                hit = idx
        if hit is not None:
            # Click = intent to select: make clicked card front + commit.
            self._front = hit
            self.queue_draw()
            self._commit_selection()

    def emit_selection(self):
        if self._paths:
            self.on_select(self._paths[self._selection])

    # -- sizing --

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 560, 900, -1, -1
        return 380, 520, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0 or not self._paths:
            return

        pivot_x, pivot_y, radius, step, start_angle = self._geometry()
        n = len(self._paths)

        # Paint order: angularly-outermost first, front (rel=0) last, so
        # the top card is drawn on top and stays readable.
        rels = sorted(range(-(n // 2), n - (n // 2)), key=lambda r: -abs(r))
        for rel in rels:
            idx = (self._front + rel) % n
            bx, by, angle = self._card_rect(pivot_x, pivot_y, radius, start_angle, step, rel)

            # Virtualization: skip cards entirely off-screen.
            if bx < -CARD_WIDTH or bx > width + CARD_WIDTH or \
               by < -CARD_HEIGHT or by > height + CARD_HEIGHT:
                continue

            path = self._paths[idx]
            selected = idx == self._selection
            focused = idx == self._front and not selected

            transform = Gsk.Transform.new()
            transform = transform.translate(Graphene.Point().init(bx, by))
            transform = transform.rotate(math.degrees(angle))

            snapshot.save()
            snapshot.transform(transform)
            draw_card(snapshot, -CARD_WIDTH / 2.0, -CARD_HEIGHT, CARD_WIDTH, CARD_HEIGHT,
                      self._textures.get(path), selected, focused,
                      self.get_style_context())
            # Approximate hover cue on the front card, same reasoning as
            # cylindrical_ring.py's equivalent: precise per-card hover
            # would need the same hit-test math as _on_click on every
            # mouse-move, so this brightens the one card a click would
            # actually act on instead.
            if self._hovered and idx == self._front and not selected:
                hover_rect = Graphene.Rect().init(-CARD_WIDTH / 2.0, -CARD_HEIGHT, CARD_WIDTH, CARD_HEIGHT)
                hover_overlay = Gdk.RGBA()
                hover_overlay.parse("rgba(255,255,255,0.10)")
                snapshot.append_color(hover_overlay, hover_rect)
            snapshot.restore()


class RadialFanLayout(WallLayout):
    display_name = "Radial Fan-Out"
    performance_tier = "slow"

    def build(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_vexpand(True)
        outer.set_hexpand(True)

        self.fan = _FanWidget()
        self.fan.on_select = self._on_select
        outer.append(self.fan)

        hint = Gtk.Label(label="Scroll or press ← / → to browse the fan; click a card to select")
        hint.add_css_class("dim-label")
        outer.append(hint)

        return outer

    def on_activate(self):
        self.fan.grab_focus()

    def _apply_wallpapers(self, paths: list[str]):
        self.fan.set_paths(paths)

    def _on_select(self, path):
        self.emit("wallpaper-selected", path)