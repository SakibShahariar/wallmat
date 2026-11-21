"""Tests for the pure colour-family classifier (no GTK dependency)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from color_palette import (
    FAMILIES, PaletteCache, classify_pixels, classify_rgb,
)


class ColorPaletteTests(unittest.TestCase):
    def test_classify_rgb_basic_families(self):
        self.assertEqual(classify_rgb(220, 30, 30), "red")
        self.assertEqual(classify_rgb(230, 130, 20), "orange")
        self.assertEqual(classify_rgb(30, 180, 60), "green")
        self.assertEqual(classify_rgb(30, 100, 220), "blue")
        self.assertEqual(classify_rgb(10, 10, 10), "dark")
        self.assertEqual(classify_rgb(250, 250, 250), "light")

    def test_classify_pixels_weights_and_ignores_noise(self):
        # One red pixel in a hundred green ones must not count as red.
        pixels = [(30, 180, 60)] * 99 + [(220, 30, 30)]
        families = classify_pixels(pixels)
        self.assertIn("green", families)
        self.assertNotIn("red", families)
        self.assertTrue(families.issubset(set(FAMILIES)))

    def test_precision_threshold(self):
        # A family needs a meaningful share (15%) to count: a 10% sprinkle
        # must not match, a 20% presence must.
        base = [(30, 180, 60)] * 90
        self.assertNotIn("red", classify_pixels(base + [(220, 30, 30)] * 10))
        self.assertIn("red", classify_pixels(base + [(220, 30, 30)] * 20))

    def test_default_sample_size_is_stable(self):
        from color_palette import extract_families
        import inspect
        self.assertEqual(
            inspect.signature(extract_families).parameters["size"].default, 32
        )

    def test_empty_pixels(self):
        self.assertEqual(classify_pixels([]), frozenset())

    def test_cache_invalidation_and_bounding(self):
        cache = PaletteCache(max_entries=2)
        cache.put("a", (1, 10), frozenset({"red"}))
        cache.put("b", (2, 20), frozenset({"blue"}))
        self.assertEqual(cache.get("a", (1, 10)), frozenset({"red"}))
        self.assertIsNone(cache.get("a", (9, 10)))  # changed fingerprint
        cache.put("a", (1, 10), frozenset({"red"}))
        cache.put("c", (3, 30), frozenset({"green"}))
        self.assertIsNone(cache.get("b", (2, 20)))  # evicted
        self.assertEqual(len(cache), 2)


if __name__ == "__main__":
    unittest.main()
