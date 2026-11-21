"""Colour-family classification for wallpaper thumbnails.

The pure helpers have no GTK dependency so they can be unit-tested in the
CI job. Image decoding imports GdkPixbuf lazily inside extract_families().
"""

import colorsys
import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable

# GdkPixbuf is loaded lazily so the pure classifier stays importable in the
# dependency-light CI job. Once loaded it is cached at module scope so the
# palette worker thread never has to import GI modules itself.
_GdkPixbuf = None


def ensure_pixbuf_loaded():
    """Load and cache GdkPixbuf. Call this on the GTK main thread."""
    global _GdkPixbuf
    if _GdkPixbuf is None:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf as _Pixbuf
        _GdkPixbuf = _Pixbuf
    return _GdkPixbuf

FAMILIES = (
    "dark", "light", "red", "orange", "yellow", "green",
    "cyan", "blue", "purple", "pink",
)

# Hue ranges in degrees. Boundaries overlap slightly so a colour near an
# edge counts for both neighbouring families.
_HUE_RANGES = (
    ("red", 345, 15),
    ("orange", 10, 45),
    ("yellow", 40, 70),
    ("green", 70, 165),
    ("cyan", 165, 200),
    ("blue", 195, 255),
    ("purple", 250, 290),
    ("pink", 290, 345),
)

# A family must own a meaningful share of the image to count. At 8% almost
# every photo matched "red"/"dark"; 15% keeps clearly-dominant families
# while still allowing multi-colour wallpapers to match more than one.
_MIN_FAMILY_WEIGHT = 0.15


def classify_rgb(red: int, green: int, blue: int) -> str | None:
    """Return the colour family for one pixel, or None for neutral/dark."""
    r, g, b = red / 255.0, green / 255.0, blue / 255.0
    hue, light, saturation = colorsys.rgb_to_hls(r, g, b)
    if light < 0.18:
        return "dark"
    if light > 0.86:
        return "light"
    if saturation < 0.16:
        return "light" if light > 0.55 else "dark"
    degrees = hue * 360.0
    for name, low, high in _HUE_RANGES:
        if low <= degrees <= high or (low > high and (degrees >= low or degrees <= high)):
            return name
    return None


def classify_pixels(pixels: Iterable[tuple[int, int, int]]) -> frozenset[str]:
    """Return the dominant colour families present in a small image."""
    weights = {name: 0.0 for name in FAMILIES}
    total = 0.0
    for red, green, blue in pixels:
        family = classify_rgb(red, green, blue)
        total += 1.0
        if family is not None:
            weights[family] += 1.0
    if total <= 0:
        return frozenset()
    return frozenset(
        name for name, weight in weights.items()
        if weight / total >= _MIN_FAMILY_WEIGHT
    )


def extract_families(path: str, size: int = 32, cache_path: str | None = None) -> frozenset[str]:
    """Decode a tiny copy of an image and classify its colour families.

    ``cache_path`` may point at an already-generated thumbnail; decoding a
    cached 480px WebP is ~20x faster than decoding a full-resolution photo,
    which keeps large libraries responsive. Falls back to the source file.
    """
    source = cache_path if cache_path and os.path.isfile(cache_path) else path
    pixbuf = ensure_pixbuf_loaded().Pixbuf.new_from_file_at_scale(
        source, size, size, True
    )
    if pixbuf is None:
        return frozenset()
    pixels = []
    rowstride = pixbuf.get_rowstride()
    channels = pixbuf.get_n_channels()
    data = pixbuf.get_pixels()
    for y in range(pixbuf.get_height()):
        row = y * rowstride
        for x in range(pixbuf.get_width()):
            offset = row + x * channels
            pixels.append((data[offset], data[offset + 1], data[offset + 2]))
    return classify_pixels(pixels)


@dataclass(frozen=True)
class PaletteEntry:
    fingerprint: tuple[int, int]
    families: frozenset[str]


class PaletteCache:
    """Bounded LRU keyed by path, invalidated by (mtime_ns, size)."""

    def __init__(self, max_entries: int = 512):
        self._max_entries = max_entries
        self._entries: OrderedDict[str, PaletteEntry] = OrderedDict()

    def get(self, path: str, fingerprint: tuple[int, int]) -> frozenset[str] | None:
        entry = self._entries.get(path)
        if entry is None:
            return None
        if entry.fingerprint != fingerprint:
            self._entries.pop(path, None)
            return None
        self._entries.move_to_end(path)
        return entry.families

    def put(self, path: str, fingerprint: tuple[int, int],
            families: frozenset[str]) -> None:
        self._entries[path] = PaletteEntry(fingerprint, families)
        self._entries.move_to_end(path)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
