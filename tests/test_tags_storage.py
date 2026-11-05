"""Tests for portable per-wallpaper tag storage."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tags_storage import decode_tags, encode_tags, normalize_tags


class TagsStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "Wallpapers"
        self.root.mkdir()
        self.wallpaper = self.root / "lake.png"
        self.wallpaper.touch()

    def tearDown(self):
        self.temp.cleanup()

    def test_normalizes_and_deduplicates_case_insensitively(self):
        self.assertEqual(
            normalize_tags([" Nature ", "nature", "  blue   hour "]),
            ["blue hour", "Nature"],
        )

    def test_set_input_is_deterministic(self):
        self.assertEqual(
            normalize_tags({"nature", "Nature", "blue"}),
            ["blue", "Nature"],
        )

    def test_rejects_invalid_tag_values(self):
        for tags in ([""], ["x" * 41], ["has,comma"], [None]):
            with self.subTest(tags=tags):
                with self.assertRaises(ValueError):
                    normalize_tags(tags)

    def test_round_trip_relative_and_external_paths(self):
        external = self.base / "outside.png"
        external.touch()
        source = {
            str(self.wallpaper): {"Nature", "Blue hour"},
            str(external): ["Minimal"],
        }
        encoded = encode_tags(source, str(self.root))
        self.assertEqual(encoded["paths"], {"lake.png": ["Blue hour", "Nature"]})
        self.assertEqual(
            decode_tags(encoded, str(self.root)),
            {
                str(self.wallpaper): {"Blue hour", "Nature"},
                str(external): {"Minimal"},
            },
        )

    def test_rebases_tags_when_old_root_is_moved(self):
        old_root = self.base / "old"
        new_root = self.base / "new"
        moved = new_root / "landscape" / "lake.png"
        moved.parent.mkdir(parents=True)
        moved.touch()
        encoded = {
            "version": 1,
            "root": str(old_root),
            "paths": {"landscape/lake.png": ["Nature"]},
            "external_paths": {},
        }
        self.assertEqual(
            decode_tags(encoded, str(new_root)),
            {str(moved): {"Nature"}},
        )

    def test_preserves_original_path_when_old_root_still_exists(self):
        old_root = self.base / "old"
        old_root.mkdir()
        new_root = self.base / "new"
        new_root.mkdir()
        encoded = {
            "version": 1,
            "root": str(old_root),
            "paths": {"lake.png": ["Nature"]},
            "external_paths": {},
        }
        self.assertEqual(
            decode_tags(encoded, str(new_root)),
            {str(old_root / "lake.png"): {"Nature"}},
        )

    def test_rejects_relative_saved_root(self):
        invalid = {
            "version": 1,
            "root": "relative/root",
            "paths": {},
            "external_paths": {},
        }
        with self.assertRaises(ValueError):
            decode_tags(invalid, str(self.root))

    def test_rejects_path_traversal_and_unknown_version(self):
        invalid = {
            "version": 1,
            "root": str(self.root),
            "paths": {"../outside.png": ["Nature"]},
            "external_paths": {},
        }
        with self.assertRaises(ValueError):
            decode_tags(invalid, str(self.root))
        invalid["version"] = 2
        with self.assertRaises(ValueError):
            decode_tags(invalid, str(self.root))

    def test_rejects_unexpected_fields_and_noncanonical_paths(self):
        invalid = {
            "version": 1,
            "root": str(self.root),
            "paths": {"folder/../lake.png": ["Nature"]},
            "external_paths": {},
        }
        with self.assertRaises(ValueError):
            decode_tags(invalid, str(self.root))
        invalid["paths"] = {}
        invalid["unexpected"] = True
        with self.assertRaises(ValueError):
            decode_tags(invalid, str(self.root))

    def test_rejects_invalid_tag_payload(self):
        invalid = {
            "version": 1,
            "root": str(self.root),
            "paths": {"lake.png": ["bad,tag"]},
            "external_paths": {},
        }
        with self.assertRaises(ValueError):
            decode_tags(invalid, str(self.root))


if __name__ == "__main__":
    unittest.main()
