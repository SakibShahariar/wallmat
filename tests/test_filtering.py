"""Tests for wallpaper filter composition (#74)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filtering import apply_filters


ROOT = "/wallpapers"
A = f"{ROOT}/red.jpg"
B = f"{ROOT}/nested/blue.jpg"
C = f"{ROOT}/green.jpg"
PATHS = [A, B, C]
PALETTES = {A: frozenset({"red"}), B: frozenset({"blue"}), C: frozenset({"green"})}


def palette_for(path):
    return PALETTES.get(path)


class FilterCompositionTests(unittest.TestCase):
    def test_no_filters_returns_everything(self):
        self.assertEqual(apply_filters(PATHS, root=ROOT), PATHS)

    def test_color_family_filters(self):
        self.assertEqual(
            apply_filters(PATHS, color_family="blue",
                          palette_for=palette_for, root=ROOT),
            [B],
        )

    def test_missing_palette_excludes_path_without_error(self):
        self.assertEqual(
            apply_filters(PATHS, color_family="pink",
                          palette_for=palette_for, root=ROOT),
            [],
        )

    def test_color_composes_with_text_search(self):
        self.assertEqual(
            apply_filters(PATHS, color_family="blue", query="NESTED",
                          palette_for=palette_for, root=ROOT),
            [B],
        )
        self.assertEqual(
            apply_filters(PATHS, color_family="blue", query="red",
                          palette_for=palette_for, root=ROOT),
            [],
        )

    def test_color_composes_with_favorites(self):
        self.assertEqual(
            apply_filters(PATHS, favorites={A, B}, color_family="blue",
                          palette_for=palette_for, root=ROOT),
            [B],
        )
        self.assertEqual(
            apply_filters(PATHS, favorites={A}, color_family="blue",
                          palette_for=palette_for, root=ROOT),
            [],
        )

    def test_color_composes_with_tag_filter(self):
        tags = {A: {"warm"}, B: {"cool", "night"}, C: {"cool"}}
        self.assertEqual(
            apply_filters(PATHS, tags=tags, tag="COOL", color_family="blue",
                          palette_for=palette_for, root=ROOT),
            [B],
        )

    def test_all_filters_together(self):
        tags = {A: {"warm"}, B: {"cool"}, C: {"cool"}}
        self.assertEqual(
            apply_filters(
                PATHS, favorites={B, C}, tags=tags, tag="cool",
                color_family="blue", query="blue", palette_for=palette_for,
                root=ROOT,
            ),
            [B],
        )

    def test_search_matches_basename_relative_path_and_tags(self):
        tags = {B: {"night"}}
        for query in ("blue", "nested/blue", "night"):
            with self.subTest(query=query):
                self.assertEqual(
                    apply_filters(PATHS, tags=tags, query=query, root=ROOT),
                    [B],
                )


if __name__ == "__main__":
    unittest.main()
