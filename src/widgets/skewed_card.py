"""
SkewedCard: a custom Gtk.Widget that draws a texture inside a skewed frame,
using Gsk.Transform matrices (GTK4 has no CSS skewX() equivalent).

Counter-skew pattern:
  outer transform: skew the "frame" by skew_deg
  inner transform: skew back by -skew_deg + scale up, so the image stays
                    upright and covers the skewed frame's corners

Also supports a "prominence" factor (0.0 - 1.0) used for center-active
scaling in the carousel: 1.0 = fully active/centered, 0.0 = fully at rest.
"""

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gtk, Gsk, Graphene, GObject, Gdk

from .gsk_utils import get_accent_rgba, get_focus_ring_rgba, get_selection_border_rgba


def natural_width(base_width: float, base_height: float, skew_deg: float = -12.0) -> int:
    """
    The exact natural HORIZONTAL width SkewedCard.do_measure() returns
    for a given base_width/base_height/skew_deg — factored out here so
    other code (e.g. infinite_ribbon.py's manual scroll-position math)
    can reproduce this number exactly instead of guessing independently.
    A previous version of that scroll math omitted this skew_pad term
    entirely, using base_width alone, which undershot the true per-card
    width enough to visibly land the initial scroll position in the
    wrong place.
    """
    skew_pad = int(abs(math.tan(math.radians(skew_deg))) * base_height)
    return base_width + skew_pad


def _get_accent_rgba() -> Gdk.RGBA:
    # Backward-compat alias — accent color logic moved to gsk_utils.get_accent_rgba().
    return get_accent_rgba()


class SkewedCard(Gtk.Widget):
    __gtype_name__ = "SkewedCard"

    def __init__(self, skew_deg: float = -12.0, base_width: int = 200, base_height: int = 260):
        super().__init__()
        self._texture: Gdk.Texture | None = None
        self._skew_deg = skew_deg
        self._base_width = base_width
        self._base_height = base_height

        # 0.0 (background item) -> 1.0 (fully centered/active item)
        self._prominence = 0.0
        # Whether this card is the ListView's currently-selected item —
        # separate from prominence (which tracks scroll-centeredness).
        # Drives a highlight border drawn inside the skewed coordinate
        # space, so it visually matches the card's shape instead of the
        # rectangular highlight GTK's default row selection would draw.
        self._selected = False
        # Keyboard focus: an inset ring (distinct from the solid selection
        # border) marking "this is the card Enter would select next".
        self._focused = False
        # Global toggle, wired up to org.gnome.desktop.interface.enable-animations
        self.animations_enabled = True

        self.set_overflow(Gtk.Overflow.VISIBLE)

        # Redraw when the system accent color changes, so an already-open
        # window updates its selection border live instead of only
        # picking up the new color on next launch.
        try:
            gi.require_version("Adw", "1")
            from gi.repository import Adw
            style_manager = Adw.StyleManager.get_default()
            style_manager.connect("notify::accent-color", lambda *a: self.queue_draw())
        except Exception:
            pass

    # -- public API used by the carousel / bind logic --

    @property
    def texture(self) -> Gdk.Texture | None:
        return self._texture

    @texture.setter
    def texture(self, value: Gdk.Texture | None):
        self._texture = value
        self.queue_draw()

    def set_prominence(self, value: float):
        value = max(0.0, min(1.0, value))
        if value != self._prominence:
            self._prominence = value
            self.queue_draw()

    def set_selected(self, value: bool):
        if value != self._selected:
            self._selected = value
            self.queue_draw()

    def set_focused(self, value: bool):
        if value != self._focused:
            self._focused = value
            self.queue_draw()

    # -- sizing --

    def do_measure(self, orientation, for_size):
        try:
            if orientation == Gtk.Orientation.HORIZONTAL:
                minimum = natural = natural_width(self._base_width, self._base_height, self._skew_deg)
            else:
                minimum = natural = self._base_height

            return minimum, natural, -1, -1
        except Exception:
            # If this ever silently fails, GTK falls back to default sizing
            # (which looked like cards stretching to divide the container
            # evenly, no gaps, no skew — exactly the bug reported). Printing
            # here turns a silent fallback into a visible diagnostic.
            import traceback
            traceback.print_exc()
            return 0, 0, -1, -1

    # -- drawing --

    def do_snapshot(self, snapshot: Gtk.Snapshot):
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return

        # Scale factor driven by center-active prominence: active card is
        # up to 20% larger than resting cards. Skipped entirely when
        # animations are disabled, per enable-animations gsetting.
        prominence_scale = 1.0
        if self.animations_enabled:
            prominence_scale = 1.0 + (0.20 * self._prominence)

        skew_deg = self._skew_deg
        # Active (centered) card straightens out — this also doubles as
        # an accessibility affordance: the focused/active item is never
        # skewed, only resting items are.
        if self.animations_enabled:
            skew_deg = self._skew_deg * (1.0 - self._prominence)

        skew_rad = math.radians(skew_deg)
        tan_skew = math.tan(skew_rad)

        center = Graphene.Point().init(width / 2.0, height / 2.0)

        outer_matrix = Graphene.Matrix()
        outer_matrix.init_from_2d(1.0, 0.0, tan_skew, 1.0, 0.0, 0.0)

        outer_transform = Gsk.Transform.new()
        outer_transform = outer_transform.translate(center)
        outer_transform = outer_transform.scale(prominence_scale, prominence_scale)
        outer_transform = outer_transform.matrix(outer_matrix)
        outer_transform = outer_transform.translate(
            Graphene.Point().init(-width / 2.0, -height / 2.0)
        )

        snapshot.save()
        snapshot.transform(outer_transform)

        # Card background/frame (visible even before texture loads)
        frame_rect = Graphene.Rect().init(0, 0, width, height)
        frame_color = Gdk.RGBA()
        frame_color.parse("#2e2e2e")
        snapshot.append_color(frame_color, frame_rect)

        # Clip everything drawn from here to the card's own skewed outline.
        # Without this, the overscanned texture below (deliberately drawn
        # larger than the card, to cover corners after counter-skewing)
        # had nothing constraining it to the card's shape — since this
        # widget uses Gtk.Overflow.VISIBLE, GTK doesn't auto-clip it
        # either, so it was bleeding into neighboring cards. This clip is
        # also what makes the image itself take on the skewed parallelogram
        # shape the border traces, instead of floating as an unrelated
        # unskewed rectangle behind/beside it.
        clip_rounded = Gsk.RoundedRect()
        clip_rounded.init_from_rect(frame_rect, 0)
        snapshot.push_rounded_clip(clip_rounded)

        if self._texture is not None:
            tex_w = self._texture.get_width()
            tex_h = self._texture.get_height()

            inner_matrix = Graphene.Matrix()
            inner_matrix.init_from_2d(1.0, 0.0, -tan_skew, 1.0, 0.0, 0.0)

            inner_transform = Gsk.Transform.new()
            inner_transform = inner_transform.translate(center)
            inner_transform = inner_transform.matrix(inner_matrix)

            snapshot.save()
            snapshot.transform(inner_transform)

            if tex_w > 0 and tex_h > 0:
                # Cover-fit + a 15% overscan margin so the counter-skewed
                # image still covers the card's corners fully. Sizing the
                # draw rect from the texture's own aspect ratio (instead
                # of stretching to width x height) is what fixes images
                # looking squished/distorted when their aspect ratio
                # doesn't match the card's.
                overscan = 1.15
                cover_scale = max((width * overscan) / tex_w, (height * overscan) / tex_h)
                draw_w = tex_w * cover_scale
                draw_h = tex_h * cover_scale
                tex_rect = Graphene.Rect().init(-draw_w / 2.0, -draw_h / 2.0, draw_w, draw_h)
            else:
                tex_rect = Graphene.Rect().init(-width * 0.575, -height * 0.575, width * 1.15, height * 1.15)

            snapshot.append_texture(self._texture, tex_rect)
            snapshot.restore()

        snapshot.pop()  # end the frame_rect clip

        border_rect = Gsk.RoundedRect()
        border_rect.init_from_rect(frame_rect, 0)

        if self._selected:
            # Drawn here, still inside outer_transform's skewed coordinate
            # space, so the border itself skews along with the card —
            # this replaces GTK's default rectangular row-selection
            # highlight, which didn't match the card's skewed shape. Color
            # follows the theme's theme_selected_bg_color (not the accent).
            accent = get_selection_border_rgba(self.get_style_context())
            border_width = 3.0
            snapshot.append_border(
                border_rect,
                [border_width, border_width, border_width, border_width],
                [accent, accent, accent, accent],
            )
        elif self._focused:
            # On the card edge, exactly like the selection border above
            # (not inset into the image) — focus vs selection is told
            # apart by a thinner, semi-transparent stroke. Color resolves
            # the themeable named color wc-focus-ring from the card's own
            # style context, so user gtk.css @define-color overrides win.
            ring_color = get_focus_ring_rgba(self.get_style_context())
            ring_width = 2.0
            snapshot.append_border(
                border_rect,
                [ring_width, ring_width, ring_width, ring_width],
                [ring_color, ring_color, ring_color, ring_color],
            )

        snapshot.restore()


GObject.type_register(SkewedCard)
