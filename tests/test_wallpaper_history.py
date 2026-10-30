"""Tests for persistent applied-wallpaper history."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wallpaper_history import append_applied, for_collection


class WallpaperHistoryTests(unittest.TestCase):
    def test_appended_path_moves_to_newest_position(self):
        self.assertEqual(
            append_applied(["a.jpg", "b.jpg"], "a.jpg"),
            ["b.jpg", "a.jpg"],
        )

    def test_history_is_bounded(self):
        self.assertEqual(
            append_applied(["a", "b", "c"], "d", limit=3),
            ["b", "c", "d"],
        )

    def test_zero_limit_disables_history(self):
        self.assertEqual(append_applied(["a"], "b", limit=0), [])

    def test_empty_path_does_not_add_history(self):
        self.assertEqual(append_applied(["a"], "", limit=5), ["a"])

    def test_collection_view_filters_missing_and_other_folder_paths(self):
        self.assertEqual(
            for_collection(
                ["a.jpg", "outside.jpg", "b.jpg", "missing.jpg"],
                {"a.jpg", "b.jpg"},
            ),
            ["a.jpg", "b.jpg"],
        )

    def test_collection_view_keeps_only_newest_bounded_entries(self):
        self.assertEqual(
            for_collection(["a", "b", "c", "d"], {"a", "b", "c", "d"}, 2),
            ["c", "d"],
        )


if __name__ == "__main__":
    unittest.main()
