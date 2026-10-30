"""Tests for portable favorites storage and legacy migration."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from favorites_storage import decode_favorites, encode_favorites


class FavoritesStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_encode_stores_collection_paths_as_relative(self):
        root = self.base / "Wallpapers"
        root.mkdir()
        favorite = root / "landscape" / "lake.png"
        favorite.parent.mkdir()
        favorite.touch()
        outside = self.base / "outside.png"
        outside.touch()
        data = encode_favorites([str(favorite), str(outside)], str(root))
        self.assertEqual(data["paths"], ["landscape/lake.png"])
        self.assertEqual(data["external_paths"], [str(outside)])

    def test_decode_rebases_when_original_root_has_been_moved(self):
        old_root = self.base / "old"
        new_root = self.base / "new"
        new_favorite = new_root / "landscape" / "lake.png"
        new_favorite.parent.mkdir(parents=True)
        new_favorite.touch()
        data = {
            "version": 1,
            "root": str(old_root),
            "paths": ["landscape/lake.png"],
            "external_paths": [],
        }
        self.assertEqual(
            decode_favorites(data, str(new_root)), {str(new_favorite)}
        )

    def test_decode_keeps_original_paths_when_old_root_still_exists(self):
        old_root = self.base / "old"
        old_root.mkdir()
        new_root = self.base / "new"
        new_root.mkdir()
        data = {
            "version": 1,
            "root": str(old_root),
            "paths": ["lake.png"],
            "external_paths": [],
        }
        self.assertEqual(
            decode_favorites(data, str(new_root)),
            {str(old_root / "lake.png")},
        )

    def test_rebases_when_old_root_remains_but_favorite_moved(self):
        old_root = self.base / "old"
        old_root.mkdir()
        new_root = self.base / "new"
        new_favorite = new_root / "lake.png"
        new_favorite.parent.mkdir()
        new_favorite.touch()
        data = {
            "version": 1,
            "root": str(old_root),
            "paths": ["lake.png"],
            "external_paths": [],
        }
        self.assertEqual(
            decode_favorites(data, str(new_root)), {str(new_favorite)}
        )

    def test_legacy_absolute_list_remains_compatible(self):
        old = str(self.base / "old.png")
        self.assertEqual(decode_favorites([old], str(self.base)), {old})

    def test_rejects_unknown_version_and_path_traversal(self):
        with self.assertRaises(ValueError):
            decode_favorites({"version": 2}, str(self.base))
        data = {
            "version": 1,
            "root": str(self.base),
            "paths": ["../outside.png"],
            "external_paths": [],
        }
        with self.assertRaises(ValueError):
            decode_favorites(data, str(self.base))

    def test_round_trip_preserves_absolute_favorites(self):
        root = self.base / "collection"
        root.mkdir()
        inside = root / "one.png"
        inside.touch()
        outside = self.base / "two.png"
        outside.touch()
        encoded = encode_favorites([str(inside), str(outside)], str(root))
        self.assertEqual(
            decode_favorites(encoded, str(root)), {str(inside), str(outside)}
        )


if __name__ == "__main__":
    unittest.main()
