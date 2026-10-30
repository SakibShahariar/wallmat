"""Tests for bounded thumbnail-cache cleanup."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cache_utils import prune_cache_directory


class CachePruningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, size, mtime):
        path = self.root / name
        path.write_bytes(b"x" * size)
        os.utime(path, ns=(mtime, mtime))
        return path

    def test_removes_oldest_cache_files_until_under_limit(self):
        oldest = self.write("old.png", 5, 10)
        newest = self.write("new.webp", 5, 30)
        remaining, removed = prune_cache_directory(str(self.root), max_bytes=5)
        self.assertEqual(remaining, 5)
        self.assertEqual(removed, [str(oldest)])
        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())

    def test_leaves_non_cache_files_untouched(self):
        note = self.write("notes.txt", 100, 1)
        cache = self.write("thumb.png", 10, 2)
        remaining, removed = prune_cache_directory(str(self.root), max_bytes=0)
        self.assertEqual(remaining, 0)
        self.assertEqual(removed, [str(cache)])
        self.assertTrue(note.exists())

    def test_does_not_follow_or_remove_symlinks(self):
        target = self.write("target.png", 10, 1)
        link = self.root / "link.png"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable in this environment")
        remaining, removed = prune_cache_directory(str(self.root), max_bytes=0)
        self.assertEqual(remaining, 0)
        self.assertEqual(removed, [str(target)])
        self.assertTrue(link.is_symlink())

    def test_missing_cache_directory_is_nonfatal(self):
        remaining, removed = prune_cache_directory(
            str(self.root / "missing"), max_bytes=10
        )
        self.assertEqual((remaining, removed), (0, []))


if __name__ == "__main__":
    unittest.main()
