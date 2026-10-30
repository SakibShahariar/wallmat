"""Tests for bounded and symlink-safe wallpaper directory scanning."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wallpaper_scan import scan_wallpapers


class WallpaperScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_image(self, relative_path):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")
        return str(path)

    def test_depth_one_scans_only_root(self):
        root_image = self.write_image("root.png")
        self.write_image("child/child.jpg")
        paths, errors, truncated = scan_wallpapers(
            str(self.root), {".png", ".jpg"}, max_depth=1
        )
        self.assertEqual(paths, [root_image])
        self.assertEqual(errors, [])
        self.assertFalse(truncated)

    def test_depth_two_scans_one_nested_level(self):
        root_image = self.write_image("root.png")
        child_image = self.write_image("child/child.jpg")
        self.write_image("child/grandchild/deep.png")
        paths, errors, _ = scan_wallpapers(
            str(self.root), {".png", ".jpg"}, max_depth=2
        )
        self.assertEqual(paths, [root_image, child_image])
        self.assertEqual(errors, [])

    def test_unlimited_depth_scans_nested_directories(self):
        self.write_image("child/grandchild/deep.png")
        paths, errors, _ = scan_wallpapers(
            str(self.root), {".png"}, max_depth=0
        )
        self.assertEqual(len(paths), 1)
        self.assertEqual(errors, [])

    def test_symlinked_files_and_directories_are_skipped(self):
        target = self.write_image("target.png")
        link_file = self.root / "linked.png"
        link_dir = self.root / "linked-dir"
        try:
            link_file.symlink_to(target)
            link_dir.symlink_to(self.root / "child", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable in this environment")
        self.write_image("child/inside.png")
        paths, errors, _ = scan_wallpapers(
            str(self.root), {".png"}
        )
        self.assertEqual(paths, [target, str(self.root / "child/inside.png")])
        self.assertEqual(errors, [])

    def test_results_are_sorted_deterministically(self):
        second = self.write_image("z/second.png")
        first = self.write_image("a/first.png")
        paths, _, _ = scan_wallpapers(str(self.root), {".png"})
        self.assertEqual(paths, [first, second])

    def test_invalid_directory_is_reported(self):
        missing = self.root / "missing"
        paths, errors, _ = scan_wallpapers(str(missing), {".png"})
        self.assertEqual(paths, [])
        self.assertTrue(errors)
        self.assertIn("not an accessible directory", errors[0])

    def test_walk_permission_error_is_returned(self):
        def failing_walk(*_args, onerror=None, **_kwargs):
            def generate():
                onerror(PermissionError(13, "Permission denied", str(self.root)))
                if False:
                    yield None
            return generate()

        with patch("wallpaper_scan.os.walk", side_effect=failing_walk):
            paths, errors, _ = scan_wallpapers(str(self.root), {".png"})
        self.assertEqual(paths, [])
        self.assertTrue(any("Permission denied" in error for error in errors))

    def test_scan_limit_reports_truncation(self):
        self.write_image("a.png")
        self.write_image("b.png")
        paths, _, truncated = scan_wallpapers(
            str(self.root), {".png"}, max_wallpapers=1
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
