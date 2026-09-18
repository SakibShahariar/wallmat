"""
Shared helper for drawing a Gdk.Texture into a target rectangle using
"cover" fit semantics (like CSS background-size: cover, or GTK4's own
Gtk.ContentFit.COVER) — scale to fill the target completely while
preserving aspect ratio, cropping any overflow, centered.

Needed anywhere a texture is drawn manually via Gtk.Snapshot rather than
through a Gtk.Picture (which already handles content-fit itself). Without
this, textures get stretched to exactly fill the target rect, distorting
any image whose aspect ratio doesn't match the widget's — which is what
was happening in DesktopPreview and SkewedCard.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gtk, Gdk, Graphene, Gsk


def hide_scrollbars(scroller):
    """Hide a ScrolledWindow's scrollbars deterministically.

    CSS-based scrollbar hiding (min-width/min-height: 0) is unreliable —
    the theme controls the bar's size and wins on some properties (seen
    in parallax_gallery: the horizontal bar still allocates ~9px even
    with scoped ``.hide-scrollbar`` rules at APPLICATION priority). The
    robust approach is to hide the Gtk.Scrollbar widgets themselves: the
    scrolled window keeps scrolling (adjustments are independent of
    scrollbar visibility), so only the visual bars disappear.
    """
    def _walk(widget):
        if isinstance(widget, Gtk.Scrollbar):
            widget.set_visible(False)
            return
        child = widget.get_first_child()
        while child is not None:
            _walk(child)
            child = child.get_next_sibling()

    _walk(scroller)


_FOCUS_CSS = b"""\
@define-color wc-focus-ring rgba(120,170,255,0.55);
@define-color wc-focus-glow rgba(120,170,255,0.6);
"""

_registered_displays = set()


def register_focus_colors(display):
    """Register the named colors once per display — user gtk.css can
    override them with a matching @define-color and those take priority
    (USER > APPLICATION provider). Lookup in widget style-contexts then
    returns the overridden value, which is how the drawn widgets pick
    up the user's gtk.css override without CSS nodes of their own."""
    if display is None or display in _registered_displays:
        return
    _registered_displays.add(display)
    provider = Gtk.CssProvider()
    provider.load_from_data(_FOCUS_CSS)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def _lookup_named(style_context, name):
    """Return the resolved named color, or None if unavailable. Copies
    via parse(to_string()) to return a fresh Gdk.RGBA the caller (and its
    alpha mutation) can safely own."""
    if style_context is not None:
        result = style_context.lookup_color(name)
        if result[0]:
            fresh = Gdk.RGBA()
            fresh.parse(result[1].to_string())
            return fresh
    return None


def lookup_named_color(style_context, name, fallback):
    """Look up a @define-color from a widget's style context; fall back
    to `fallback` Gdk.RGBA if the name isn't defined. PyGObject surfaces
    the color through the (found, rgba) return tuple."""
    color = _lookup_named(style_context, name)
    return color if color is not None else fallback


def get_theme_selected_bg_rgba(style_context=None):
    """Resolve the theme's selection-background color
    (theme_selected_bg_color, used by Material-Gnome) from a realization
    style context. Falls back to the accent color."""
    color = _lookup_named(style_context, "theme_selected_bg_color")
    if color is not None:
        return color
    return get_accent_rgba()


def get_selection_border_rgba(style_context=None):
    """Color for the committed-selection border. Uses the theme's
    selection-background color so selection/focus follow the theme, not
    the libadwaita accent."""
    return get_theme_selected_bg_rgba(style_context)


def get_focus_ring_rgba(style_context=None):
    """The ring color for keyboard focus — resolves the theme's
    theme_selected_bg_color (falling back to the themeable named color
    wc-focus-ring, then the accent at 55% alpha)."""
    base = _lookup_named(style_context, "theme_selected_bg_color")
    if base is None:
        base = _lookup_named(style_context, "wc-focus-ring")
    if base is None:
        base = get_accent_rgba()
    base.alpha = 0.55
    return base


def draw_texture_cover(snapshot: Gtk.Snapshot, texture: Gdk.Texture, x: float, y: float, width: float, height: float):
    """Draw `texture` into the rect (x, y, width, height), cropped to
    fill it completely without distorting the image's aspect ratio."""
    if width <= 0 or height <= 0:
        return

    tex_w = texture.get_width()
    tex_h = texture.get_height()
    if tex_w <= 0 or tex_h <= 0:
        return

    # "Cover" scale: the larger of the two ratios, so the texture
    # overflows the target rect on one axis rather than leaving gaps.
    scale = max(width / tex_w, height / tex_h)
    draw_w = tex_w * scale
    draw_h = tex_h * scale
    offset_x = x + (width - draw_w) / 2.0
    offset_y = y + (height - draw_h) / 2.0

    clip_rect = Graphene.Rect().init(x, y, width, height)
    snapshot.push_clip(clip_rect)

    tex_rect = Graphene.Rect().init(offset_x, offset_y, draw_w, draw_h)
    snapshot.append_texture(texture, tex_rect)

    snapshot.pop()


def get_accent_rgba() -> Gdk.RGBA:
    """
    The system accent color, via libadwaita's StyleManager — this is what
    makes selection borders follow the user's GNOME accent color setting
    instead of a hardcoded value. Custom-drawn widgets bypass GTK's CSS
    engine entirely (no CSS node for a theme to attach to), so this has
    to actively query the accent color and hand back a concrete RGBA.

    Falls back to a fixed blue if Adw.StyleManager.get_accent_color_rgba()
    isn't available (needs libadwaita >= 1.6) or anything else fails.
    """
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        style_manager = Adw.StyleManager.get_default()
        return style_manager.get_accent_color_rgba()
    except Exception:
        fallback = Gdk.RGBA()
        fallback.parse("#78aaff")
        return fallback


def draw_card(snapshot, x: float, y: float, width: float, height: float,
              texture, selected: bool = False, focused: bool = False,
              style_context=None):
    """
    Draw a single themed card into the snapshot: dark frame, cover-fit
    texture, and a highlight. `selected` draws a solid accent border on
    the card edge (the committed selection); `focused` — used only when
    the card is NOT selected — draws a thinner, translucent ring on the
    same edge, so the two states are visually distinct (focus = "this is
    the next card Enter would select", selection = "this one is already
    committed"). Shared by the custom widgets that paint cards themselves
    (Cylindrical Ring, Radial Fan) so the visuals match SkewedCard.

    `style_context` is the calling widget's style context; it's used to
    resolve the themeable named color `wc-focus-ring` (which user gtk.css
    can override via @define-color). Falls back to the accent color when
    omitted.
    """
    rect = Graphene.Rect().init(x, y, width, height)

    frame_color = Gdk.RGBA()
    frame_color.parse("#2e2e2e")
    snapshot.append_color(frame_color, rect)

    if texture is not None:
        draw_texture_cover(snapshot, texture, x, y, width, height)

    frame_rounded = Gsk.RoundedRect()
    frame_rounded.init_from_rect(rect, 0)

    if selected:
        accent = get_selection_border_rgba(style_context)
        border_width = 3.0
        snapshot.append_border(
            frame_rounded,
            [border_width, border_width, border_width, border_width],
            [accent, accent, accent, accent],
        )
    elif focused:
        # Drawn on the exact same card edge the selection border uses
        # (NOT inset — an earlier version inset the ring 3px, which made
        # it float inside the image); focus is told apart from selection
        # only by being thinner and semi-transparent.
        ring_color = get_focus_ring_rgba(style_context)
        ring_width = 2.0
        snapshot.append_border(
            frame_rounded,
            [ring_width, ring_width, ring_width, ring_width],
            [ring_color, ring_color, ring_color, ring_color],
        )
