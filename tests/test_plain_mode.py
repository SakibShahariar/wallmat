"""Tests for the --plain command-line status contract."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plain_mode import (
    SUCCESS, CANCELLED, INVALID_DIRECTORY, SCAN_FAILED, validate_directory,
)


class PlainModeContractTests(unittest.TestCase):
    def test_exit_status_values_are_stable_and_distinct(self):
        self.assertEqual(
            {SUCCESS, CANCELLED, INVALID_DIRECTORY, SCAN_FAILED},
            {0, 2, 3, 4},
        )

    def test_existing_directory_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(validate_directory(directory))

    def test_missing_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing")
            self.assertIn("Not a directory", validate_directory(missing))

    def test_regular_file_is_rejected(self):
        with tempfile.NamedTemporaryFile() as handle:
            self.assertIn("Not a directory", validate_directory(handle.name))

    def test_unreadable_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("os.access", return_value=False):
                self.assertIn("not readable", validate_directory(directory))


if __name__ == "__main__":
    unittest.main()
