"""Tests for wallpaper placement mode mapping."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from placement import (
    MODES, MODE_LABELS, apply_gnome_placement, gnome_option,
    supported_modes,
)


class PlacementTests(unittest.TestCase):
    def test_all_modes_have_labels_and_gnome_options(self):
        for mode in MODES:
            self.assertIn(mode, MODE_LABELS)
            self.assertIsNotNone(gnome_option(mode))

    def test_gnome_option_values(self):
        self.assertEqual(gnome_option("fill"), "zoom")
        self.assertEqual(gnome_option("fit"), "scaled")
        self.assertEqual(gnome_option("center"), "centered")
        self.assertEqual(gnome_option("stretch"), "stretched")
        self.assertIsNone(gnome_option("bogus"))

    def test_supported_modes_depends_on_desktop_enum(self):
        options = ("none", "centered", "scaled", "stretched", "zoom")
        self.assertEqual(supported_modes(options), set(MODES))
        self.assertNotIn("stretch", supported_modes(("zoom", "scaled")))

    def test_unsupported_mode_is_rejected(self):
        class FakeSettings:
            def list_keys(self):
                return ["picture-options"]

            def get_range(self, _key):
                return ("enum", ["zoom", "scaled"])

            def set_string(self, _key, _value):
                raise AssertionError("must not write")

        self.assertFalse(apply_gnome_placement(FakeSettings(), "bogus"))
        self.assertFalse(apply_gnome_placement(FakeSettings(), "stretch"))


if __name__ == "__main__":
    unittest.main()
