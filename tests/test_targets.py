"""Tests for wallpaper target capability detection and routing (#76)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targets import (
    PORTAL_SET_ON, TARGETS, gnome_has_separate_lock_screen, portal_set_on,
    resolve_target, screensaver_keys_for_target, supported_targets,
)


class TargetTests(unittest.TestCase):
    def test_portal_set_on_values(self):
        self.assertEqual(portal_set_on("desktop"), "background")
        self.assertEqual(portal_set_on("lock"), "lockscreen")
        self.assertEqual(portal_set_on("both"), "both")
        self.assertIsNone(portal_set_on("bogus"))
        self.assertEqual(set(PORTAL_SET_ON), set(TARGETS))

    def test_no_capabilities_offers_no_targets(self):
        self.assertEqual(supported_targets([], [], False), set())

    def test_desktop_only_desktop(self):
        supported = supported_targets(["picture-uri", "picture-uri-dark"], [], False)
        self.assertEqual(supported, {"desktop"})

    def test_background_and_screensaver_offer_all_targets(self):
        supported = supported_targets(
            ["picture-uri"], ["picture-uri", "picture-options"], False
        )
        self.assertEqual(supported, {"desktop", "lock", "both"})

    def test_screensaver_alone_offers_lock_only(self):
        supported = supported_targets([], ["picture-uri"], False)
        self.assertEqual(supported, {"lock"})

    def test_gnome_40_plus_has_no_separate_lock_screen(self):
        self.assertIs(gnome_has_separate_lock_screen("51.1"), False)
        self.assertIs(gnome_has_separate_lock_screen("40.0"), False)
        self.assertIs(gnome_has_separate_lock_screen("39.3"), True)
        self.assertIsNone(gnome_has_separate_lock_screen(None))
        self.assertIsNone(gnome_has_separate_lock_screen("bogus"))

    def test_gnome_40_plus_disables_lock_targets(self):
        # Even with a screensaver key and portal set-on, GNOME 51 reuses the
        # desktop wallpaper for the lock screen, so only desktop is valid.
        supported = supported_targets(
            ["picture-uri"], ["picture-uri"], True, "51.1"
        )
        self.assertEqual(supported, {"desktop"})
        # Older GNOME still supports a separate lock screen.
        supported = supported_targets(
            ["picture-uri"], ["picture-uri"], True, "39.3"
        )
        self.assertEqual(supported, {"desktop", "lock", "both"})

    def test_portal_support_offers_all_targets(self):
        self.assertEqual(supported_targets([], [], True),
                         {"desktop", "lock", "both"})

    def test_resolve_known_target(self):
        supported = {"desktop", "lock", "both"}
        for target in TARGETS:
            self.assertEqual(resolve_target(target, supported), target)

    def test_resolve_unsupported_returns_none(self):
        self.assertIsNone(resolve_target("lock", {"desktop"}))
        self.assertIsNone(resolve_target("both", {"desktop"}))

    def test_unknown_request_defaults_to_desktop(self):
        self.assertEqual(resolve_target("bogus", {"desktop", "lock"}), "desktop")
        self.assertEqual(resolve_target("", {"desktop"}), "desktop")

    def test_screensaver_keys_by_target(self):
        self.assertEqual(screensaver_keys_for_target("desktop"), ())
        self.assertEqual(screensaver_keys_for_target("lock"), ("picture-uri",))
        self.assertEqual(screensaver_keys_for_target("both"), ("picture-uri",))


if __name__ == "__main__":
    unittest.main()
