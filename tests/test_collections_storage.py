"""Tests for named wallpaper collection storage."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collections_storage import (
    decode_collections,
    encode_collections,
    normalize_collection_name,
)


class CollectionsStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.first = self.root / "first.png"
        self.second = self.root / "second.png"
        self.first.touch()
        self.second.touch()

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_named_collections_and_order(self):
        source = {
            "Night": [str(self.first), str(self.second), str(self.first)],
            "Nature": [str(self.second)],
        }
        encoded = encode_collections(source)
        self.assertEqual(
            decode_collections(encoded),
            {
                "Nature": [str(self.second)],
                "Night": [str(self.first), str(self.second)],
            },
        )

    def test_normalizes_collection_names(self):
        self.assertEqual(normalize_collection_name("  Dark   wallpapers "), "Dark wallpapers")

    def test_rejects_duplicate_names_ignoring_case(self):
        with self.assertRaises(ValueError):
            encode_collections({"Nature": [], "nature": []})

    def test_rejects_invalid_names_and_relative_paths(self):
        for name in ("", "x" * 49, "../escape", "path/name", "path\\name"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    normalize_collection_name(name)
        with self.assertRaises(ValueError):
            encode_collections({"Nature": ["relative.png"]})

    def test_rejects_unknown_fields_and_versions(self):
        data = encode_collections({"Nature": [str(self.first)]})
        data["extra"] = True
        with self.assertRaises(ValueError):
            decode_collections(data)
        data = encode_collections({"Nature": []})
        data["version"] = True
        with self.assertRaises(ValueError):
            decode_collections(data)


if __name__ == "__main__":
    unittest.main()
