"""Tests for resolution-based wallpaper ordering."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wallpaper_sort import sort_by_resolution


class WallpaperSortTests(unittest.TestCase):
    def test_largest_pixel_area_sorts_first(self):
        dimensions = {
            "small.png": (800, 600),
            "wide.png": (1920, 1080),
            "large.png": (3840, 2160),
        }
        result = sort_by_resolution(
            list(dimensions), dimensions.__getitem__
        )
        self.assertEqual(result, ["large.png", "wide.png", "small.png"])

    def test_equal_dimensions_use_stable_path_order(self):
        dimensions = {
            "z.png": (1920, 1080),
            "a.png": (1920, 1080),
        }
        self.assertEqual(
            sort_by_resolution(["z.png", "a.png"], dimensions.__getitem__),
            ["a.png", "z.png"],
        )

    def test_unknown_dimensions_are_last(self):
        dimensions = {"known.png": (1920, 1080)}
        def get_dimensions(path):
            return dimensions.get(path)
        self.assertEqual(
            sort_by_resolution(["unknown.png", "known.png"], get_dimensions),
            ["known.png", "unknown.png"],
        )

    def test_invalid_dimension_data_is_last(self):
        def get_dimensions(path):
            if path == "bad.png":
                return (0, 0)
            return (1280, 720)
        self.assertEqual(
            sort_by_resolution(["bad.png", "good.png"], get_dimensions),
            ["good.png", "bad.png"],
        )


if __name__ == "__main__":
    unittest.main()
