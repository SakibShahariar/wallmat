"""Unit tests for recent-aware random wallpaper selection."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from random_selection import choose_next, shuffle_with_recent_last


def first(items):
    return items[0]


class RandomSelectionTests(unittest.TestCase):
    def test_excludes_recent_paths_when_alternatives_exist(self):
        selected, history = choose_next(
            ["/a.jpg", "/b.jpg", "/c.jpg"],
            ["/a.jpg"],
            2,
            chooser=first,
        )
        self.assertEqual(selected, "/b.jpg")
        self.assertEqual(history, ["/b.jpg", "/a.jpg"])

    def test_resets_when_candidate_pool_is_exhausted(self):
        selected, history = choose_next(
            ["/a.jpg", "/b.jpg"],
            ["/a.jpg", "/b.jpg"],
            2,
            chooser=first,
        )
        self.assertEqual(selected, "/a.jpg")
        self.assertEqual(history, ["/a.jpg"])

    def test_history_is_bounded_and_ignores_paths_outside_pool(self):
        selected, history = choose_next(
            ["/a.jpg", "/b.jpg", "/c.jpg"],
            ["/missing.jpg", "/a.jpg", "/b.jpg"],
            2,
            chooser=first,
        )
        self.assertEqual(selected, "/c.jpg")
        self.assertEqual(history, ["/c.jpg", "/a.jpg"])

    def test_zero_history_limit_allows_every_candidate(self):
        selected, history = choose_next(
            ["/a.jpg", "/b.jpg"],
            ["/a.jpg"],
            0,
            chooser=first,
        )
        self.assertEqual(selected, "/a.jpg")
        self.assertEqual(history, [])

    def test_empty_candidate_pool_returns_no_selection(self):
        self.assertEqual(choose_next([], ["/a.jpg"], 5), (None, []))

    def test_random_sort_keeps_recent_paths_at_the_end(self):
        ordered = shuffle_with_recent_last(
            ["/a.jpg", "/b.jpg", "/c.jpg"],
            ["/a.jpg"],
            shuffler=lambda items: None,
        )
        self.assertEqual(ordered, ["/b.jpg", "/c.jpg", "/a.jpg"])


if __name__ == "__main__":
    unittest.main()
