"""Tests for accessible wallpaper names."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from widgets.accessibility import wallpaper_accessible_name


class WallpaperAccessibleNameTests(unittest.TestCase):
    def test_includes_parent_folder_for_context(self):
        self.assertEqual(
            wallpaper_accessible_name("/home/user/Wallpapers/Nature/forest.png"),
            "forest.png, in Nature",
        )

    def test_handles_simple_and_empty_names(self):
        self.assertEqual(wallpaper_accessible_name("forest.png"), "forest.png")
        self.assertEqual(wallpaper_accessible_name(""), "Wallpaper thumbnail")
        self.assertEqual(wallpaper_accessible_name(None), "Wallpaper thumbnail")


if __name__ == "__main__":
    unittest.main()
