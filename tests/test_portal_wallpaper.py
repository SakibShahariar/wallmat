"""Pure protocol-result tests for the XDG wallpaper portal adapter."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from portal_wallpaper import is_portal_unavailable_error, portal_response_result


class PortalWallpaperTests(unittest.TestCase):
    def test_maps_success_cancel_and_failure_responses(self):
        self.assertEqual(portal_response_result(0), (True, None))
        self.assertEqual(
            portal_response_result(1),
            (False, "The wallpaper change was cancelled in the desktop portal."),
        )
        self.assertEqual(
            portal_response_result(2),
            (False, "The desktop portal could not set the wallpaper."),
        )

    def test_unknown_response_is_a_failure(self):
        result, message = portal_response_result(99)
        self.assertFalse(result)
        self.assertIn("99", message)

    def test_only_unavailable_portal_errors_trigger_fallback(self):
        self.assertTrue(
            is_portal_unavailable_error("org.freedesktop.DBus.Error.ServiceUnknown")
        )
        self.assertTrue(
            is_portal_unavailable_error("org.freedesktop.DBus.Error.UnknownMethod")
        )
        self.assertTrue(
            is_portal_unavailable_error("org.freedesktop.DBus.Error.NoReply")
        )
        self.assertTrue(
            is_portal_unavailable_error("org.freedesktop.DBus.Error.NotSupported")
        )
        self.assertFalse(
            is_portal_unavailable_error("org.freedesktop.portal.Error.NotAllowed")
        )


if __name__ == "__main__":
    unittest.main()
