"""Tests for versioned Wallmat backup validation and round trips."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backup_storage import decode_backup, encode_backup


class BackupStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "wallpapers"
        self.root.mkdir()
        self.favorite = self.root / "lake.png"
        self.favorite.touch()

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_favorites_and_preferences(self):
        preferences = {
            "selected-layout": "masonry_grid",
            "sort-mode": "resolution",
            "favorites-only": True,
            "scan-depth": 2,
            "recent-wallpapers": [str(self.favorite)],
        }
        tags = {str(self.favorite): {"Nature", "Blue hour"}}
        collections = {"Nature": [str(self.favorite)]}
        backup = encode_backup(
            {str(self.favorite)}, str(self.root), preferences, tags, collections
        )
        restored = decode_backup(backup, str(self.root))
        self.assertEqual(restored["favorites"], {str(self.favorite)})
        self.assertEqual(restored["preferences"], preferences)
        self.assertEqual(
            restored["tags"], {str(self.favorite): {"Blue hour", "Nature"}}
        )
        self.assertEqual(
            restored["collections"], {"Nature": [str(self.favorite)]}
        )

    def test_rejects_invalid_tags_mapping(self):
        with self.assertRaises(ValueError):
            encode_backup(set(), str(self.root), {}, tags=[])
        with self.assertRaises(ValueError):
            encode_backup(set(), str(self.root), {}, collections=[])

    def test_decodes_version_one_backup_without_erasing_tags(self):
        data = {
            "format": "dev.sakib.Wallmat.backup",
            "version": 1,
            "favorites": {
                "version": 1,
                "root": str(self.root),
                "paths": ["lake.png"],
                "external_paths": [],
            },
            "preferences": {"last-filter": "blue"},
        }
        restored = decode_backup(data, str(self.root))
        self.assertIsNone(restored["tags"])
        self.assertEqual(restored["favorites"], {str(self.favorite)})

    def test_decodes_version_two_backup_without_erasing_collections(self):
        data = encode_backup(set(), str(self.root), {})
        data["version"] = 2
        data.pop("collections")
        restored = decode_backup(data, str(self.root))
        self.assertIsNone(restored["collections"])

    def test_accepts_partial_preferences(self):
        backup = encode_backup(set(), str(self.root), {"last-filter": "blue"})
        self.assertEqual(
            decode_backup(backup, str(self.root))["preferences"],
            {"last-filter": "blue"},
        )

    def test_rejects_wrong_format_and_version(self):
        with self.assertRaises(ValueError):
            decode_backup({"format": "other", "version": 1}, str(self.root))
        data = encode_backup(set(), str(self.root), {})
        data["version"] = True
        with self.assertRaises(ValueError):
            decode_backup(data, str(self.root))

    def test_rejects_unknown_top_level_fields(self):
        data = encode_backup(set(), str(self.root), {})
        data["credentials"] = {"token": "never"}
        with self.assertRaises(ValueError):
            decode_backup(data, str(self.root))

    def test_rejects_unknown_preference_keys(self):
        data = encode_backup(set(), str(self.root), {})
        data["preferences"]["unknown-setting"] = "value"
        with self.assertRaises(ValueError):
            decode_backup(data, str(self.root))

    def test_rejects_invalid_preference_types_and_ranges(self):
        for key, value in (
            ("favorites-only", 1),
            ("scan-depth", 21),
            ("auto-rotate-interval", 30),
            ("auto-rotate-interval", 61),
            ("selected-layout", "not-a-layout"),
            ("sort-mode", "invalid"),
            ("recent-wallpapers", ["/valid.png", None]),
        ):
            with self.subTest(key=key):
                data = encode_backup(set(), str(self.root), {})
                data["preferences"][key] = value
                with self.assertRaises(ValueError):
                    decode_backup(data, str(self.root))

    def test_invalid_favorites_reject_entire_backup(self):
        data = encode_backup(set(), str(self.root), {"scan-depth": 2})
        data["favorites"] = {
            "version": 1,
            "root": str(self.root),
            "paths": ["../outside.png"],
            "external_paths": [],
        }
        with self.assertRaises(ValueError):
            decode_backup(data, str(self.root))

    def test_validation_does_not_mutate_input(self):
        preferences = {"recent-wallpapers": [str(self.favorite)]}
        backup = encode_backup(set(), str(self.root), preferences)
        original = list(backup["preferences"]["recent-wallpapers"])
        decode_backup(backup, str(self.root))
        self.assertEqual(backup["preferences"]["recent-wallpapers"], original)


if __name__ == "__main__":
    unittest.main()
