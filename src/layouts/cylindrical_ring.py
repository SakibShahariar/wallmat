"""
Layout #1: Cylindrical Ring Carousel (spec-ranked 8/8 — slowest, "Hard")

The spec's design calls for a genuine 3D cylinder with per-card Y-axis
rotation and perspective foreshortening. That's now implemented here:

- Cards travel along the surface of a virtual cylinder: each card's
  horizontal offset is R*sin(theta) and its depth is -R*(1-cos(theta)),
  so side cards rotate away from the viewer around the Y axis
  (Gsk.Transform.rotate_3d) and recede.
- A single Gsk.Transform.perspective() at the start of the snapshot
  gives real perspective projection instead of a flat scale — GTK's GL
  renderer handles the 3D; the Cairo/software fallback flattens
  gracefully (still scaled/shifted correctly, just not foreshortened).
- Depth order is handled by painting back-to-front: each visible card's
  z is computed, the set is sorted deepest-first, and the front (center)
  card is painted last. GTK has no z-buffer, so this manual sort is the
  required substitute — exactly what the spec warned about.
- Only cards whose projected position intersects the viewport are
  drawn at all (no ListView, but virtualization of the same kind: N
  cards per folder -> only ~6-8 ever cost anything per frame).
- Interaction: scroll to spin the ring, ←/→ to move the selected card
  to center (smoothed), click to select + emit wallpaper-selected.

The floor-reflection effect from the spec is still skipped (it would
double the snapshots per frame for marginal visual gain in a prototype).
"""

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gtk, Gdk, Graphene, Gsk, GLib

from .base import WallLayout
from announce import say
from widgets.thumbnail_loader import ThumbnailLoader
from widgets.gsk_utils import draw_card, get_animations_enabled

CARD_WIDTH = 180
CARD_HEIGHT = 240
# Horizontal gap between neighboring cards as a fraction of card width —
# cards sit *tight* on the cylinder surface; the gap keeps them readable
# instead of edge-to-edge.
CARD_GAP = 1.18

# Radians of surface angle occupied by one card. Kept roughly proportional
# to CARD_WIDTH/R so the wafer sits correctly on the ring at any size.
MAX_SURFACE_ANGLE_RAD = 1.15  # hard cut-off: past here a card is edge-on
CAMERA_DEPTH = 1200.0  # GSK perspective() camera distance

EASE_MS = 160  # center-snap animation length


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class _RingWidget(Gtk.Widget):
    __gtype_name__ = "RingWidget"

    def __init__(self):
        super().__init__()
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_size_request(360, CARD_HEIGHT + 60)

        self._textures: dict[str, Gdk.Texture] = {}
        self._paths: list[str] = []
        self._loader = ThumbnailLoader(thumb_size=480)  # cards render at 180x240
        self._center_unit = 0.0
        self._target_center: float | None = None
        self._anim_source = None
        self._selection = 0
        # Initialized here (not just inside set_paths()) so it's never
        # undefined between construction and the first set_paths() call —
        # previously only set inside set_paths(), which happened to always
        # run first in practice but was one refactor away from an
        # AttributeError on any input event that landed before it.
        self._focus = 0
        # One-shot read of the reduced-motion preference; the center-snap
        # ease below is skipped (jumps straight to the target) when the
        # user has animations disabled at the system level. Not live-
        # watched (a toggle mid-session just needs a relaunch here).
        self._animations_enabled = get_animations_enabled()
        self._hovered = False

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.HORIZONTAL)
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

        # The whole ring is one clickable surface (click selects whichever
        # card is nearest the click point) — a pointer cursor tells the
        # user that before they click, since there's no hover feedback of
        # any kind otherwise on a hand-drawn Gtk.Widget like this one.
        self.set_cursor_from_name("pointer")

        self.connect("realize", lambda w: w.grab_focus())

    def _set_hovered(self, value: bool):
        if value != self._hovered:
            self._hovered = value
            self.queue_draw()

    # -- public API --

    def set_paths(self, paths: list[str]):
        self._paths = list(paths)
        self._textures.clear()
        self._center_unit = 0.0
        self._target_center = None
        self._focus = 0
        self._selection = 0
        for path in paths:
            def on_ready(item_id, texture, path=path):
                self._textures[item_id] = texture
                self.queue_draw()

            self._loader.request(path, path, on_ready)
        self.queue_draw()

    def _center_on(self, position: int, announce: bool = False):
        """Spin the ring so `position` (path index) is front-and-center,
        updating keyboard FOCUS only. Selection is NOT touched — commit
        it explicitly with _commit_selection() (Enter or a click)."""
        n = len(self._paths)
        if n == 0:
            return
        position %= n
        self._focus = position
        self._target_center = float(self._focus)
        self._start_anim()
        if announce:
            say(f"Focus: {self._paths[self._focus]}")

    def _commit_selection(self):
        """The only paths into changing selection + emitting
        wallpaper-selected (which prints "Selected:")."""
        if not self._paths:
            return
        self._selection = self._focus
        self.on_select(self._paths[self._selection])

    def _start_anim(self):
        if not self._animations_enabled:
            # Reduced motion: snap straight to the target instead of
            # easing — this layout previously ran its center-snap tween
            # unconditionally, regardless of the system's enable-animations
            # setting (unlike the SkewedCard-based carousel layouts, which
            # already respected it).
            if self._target_center is not None:
                self._center_unit = self._target_center
                self._target_center = None
                self.queue_draw()
            return
        if self._anim_source is not None:
            return
        start_center = self._center_unit
        start_time_us = GLib.get_monotonic_time()
        duration_us = EASE_MS * 1000

        def step(_=None):
            if self._target_center is None:
                self._anim_source = None
                return GLib.SOURCE_REMOVE
            t = (GLib.get_monotonic_time() - start_time_us) / duration_us
            t = min(1.0, t)
            self._center_unit = start_center + (self._target_center - start_center) * _ease_out_cubic(t)
            self.queue_draw()
            if t >= 1.0:
                self._center_unit = self._target_center
                self._target_center = None
                self._anim_source = None
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        self._anim_source = GLib.timeout_add(16, step)

    # -- input --

    def _on_scroll(self, controller, dx, dy):
        if dx == 0:
            return False
        self._center_unit += dx / (CARD_WIDTH * CARD_GAP)
        self._target_center = None  # user takes control back from any snap anim
        if self._paths:
            # Silent focus tracking only — scrolling never selects or
            # emits wallpaper-selected. Enter commits whatever card the
            # user stopped on.
            self._focus = int(round(self._center_unit)) % len(self._paths)
        self.queue_draw()
        return True

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            if not self._paths:
                return True
            step = 1 if keyval == Gdk.KEY_Right else -1
            self._center_on(self._focus + step, announce=True)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._commit_selection()
            return True
        return False

    def _on_click(self, gesture, n_press, x, y):
        if not self._paths:
            return
        # Convert the click point back into a ring angle: the card at
        # theta has screen x = width/2 + R*sin(theta), so invert that for
        # the nearest integer card. The y axis is ignored (full height hit box).
        width = self.get_width()
        radius = self._radius()
        dx_from_center = x - width / 2.0
        rel_units = math.asin(max(-1.0, min(1.0, dx_from_center / max(1.0, radius)))) / self._card_angle()
        clicked_index = round(self._center_unit + rel_units)
        idx = clicked_index % len(self._paths)
        # Click = intent to select: center the card and commit.
        self._center_on(idx)
        self._commit_selection()

    # -- geometry helpers --

    def _radius(self):
        return max(120.0, self.get_width() * 0.36)

    def _card_angle(self):
        return (CARD_WIDTH * CARD_GAP) / self._radius()

    def _depth_z(self, theta: float):
        return -self._radius() * (1.0 - math.cos(theta))

    # -- sizing --

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 360, 760, -1, -1
        return CARD_HEIGHT, CARD_HEIGHT, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0 or not self._paths:
            return

        radius = self._radius()
        card_angle = self._card_angle()
        center_i = round(self._center_unit)
        span = int(math.ceil(MAX_SURFACE_ANGLE_RAD / card_angle)) + 1
        n = len(self._paths)

        # Collect the (few) cards near the viewport with their depth, so
        # we can paint deepest-first.
        visible = []
        for rel in range(-span, span + 1):
            index = center_i + rel
            theta = (index - self._center_unit) * card_angle
            if abs(theta) > MAX_SURFACE_ANGLE_RAD:
                continue
            screen_x = width / 2.0 + radius * math.sin(theta)
            if screen_x < -CARD_WIDTH or screen_x > width + CARD_WIDTH:
                continue
            path_idx = index % n
            visible.append((self._depth_z(theta), screen_x, path_idx, theta))
        if not visible:
            return

        visible.sort(key=lambda v: v[0])  # most negative z first -> deepest drawn first

        cy = height / 2.0

        camera = Gsk.Transform.new().perspective(CAMERA_DEPTH)
        snapshot.save()
        snapshot.transform(camera)

        axis_y = Graphene.Vec3().init(0.0, 1.0, 0.0)
        for z, screen_x, path_idx, theta in visible:
            path = self._paths[path_idx]
            texture = self._textures.get(path)
            selected = path_idx == self._selection
            focused = path_idx == self._focus and not selected

            card_transform = Gsk.Transform.new()
            card_transform = card_transform.translate_3d(
                Graphene.Point3D().init(screen_x, cy, z)
            )
            card_transform = card_transform.rotate_3d(theta, axis_y)

            snapshot.save()
            snapshot.transform(card_transform)
            draw_card(snapshot, -CARD_WIDTH / 2.0, -CARD_HEIGHT / 2.0,
                      CARD_WIDTH, CARD_HEIGHT, texture, selected, focused,
                      self.get_style_context())
            # Approximate hover cue: brighten the front card while the
            # mouse is anywhere over the widget. Precise per-card hit
            # testing on mouse-move would need the same geometry math as
            # _on_click; brightening the one card a click would actually
            # act on is a reasonable stand-in without duplicating that.
            if self._hovered and path_idx == self._focus and not selected:
                hover_rect = Graphene.Rect().init(-CARD_WIDTH / 2.0, -CARD_HEIGHT / 2.0, CARD_WIDTH, CARD_HEIGHT)
                hover_overlay = Gdk.RGBA()
                hover_overlay.parse("rgba(255,255,255,0.10)")
                snapshot.append_color(hover_overlay, hover_rect)
            snapshot.restore()

        snapshot.restore()


class CylindricalRingLayout(WallLayout):
    display_name = "Cylindrical Ring"
    performance_tier = "slow"

    def __init__(self):
        super().__init__()

    def build(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_vexpand(True)
        outer.set_hexpand(True)

        self.ring = _RingWidget()
        self.ring.on_select = self._on_select
        outer.append(self.ring)

        hint = Gtk.Label(
            label="Scroll / ← / → to browse (shifts focus) — Enter or click to select"
        )
        hint.add_css_class("dim-label")
        outer.append(hint)

        return outer

    def on_activate(self):
        self.ring.grab_focus()

    def _apply_wallpapers(self, paths: list[str]):
        self.ring.set_paths(paths)

    def _on_select(self, path):
        self.emit("wallpaper-selected", path)