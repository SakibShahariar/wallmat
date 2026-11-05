"""Tests for Matugen preview command construction and output parsing."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matugen_preview import build_preview_command, parse_preview_output


class MatugenPreviewTests(unittest.TestCase):
    def test_command_preserves_scheme_options_and_forces_dry_run_json(self):
        command = build_preview_command(
            "/wallpapers/blue.png",
            ["--type", "scheme-content", "--mode", "light"],
        )
        self.assertEqual(
            command,
            [
                "matugen", "image", "/wallpapers/blue.png",
                "--type", "scheme-content", "--mode", "light",
                "--json", "hex", "--dry-run", "--quiet",
            ],
        )

    def test_command_replaces_conflicting_json_and_dry_run_flags(self):
        command = build_preview_command(
            "/wallpapers/blue.png",
            ["--json", "rgb", "--dry-run", "--quiet", "--type", "scheme-tonal-spot"],
        )
        self.assertEqual(command.count("--json"), 1)
        self.assertEqual(command.count("--dry-run"), 1)
        self.assertEqual(command.count("--quiet"), 1)
        self.assertIn("hex", command)

    def test_parses_dark_and_light_colors_with_trailing_ok(self):
        payload = {
            "colors": {
                "primary": {
                    "dark": {"color": "#112233"},
                    "light": {"color": "#aabbcc"},
                },
                "surface": {
                    "dark": {"color": "#010203"},
                    "light": {"color": "#fefdfc"},
                },
            }
        }
        parsed = parse_preview_output(json.dumps(payload) + "\\nok")
        self.assertEqual(
            parsed,
            {
                "dark": [("primary", "#112233"), ("surface", "#010203")],
                "light": [("primary", "#aabbcc"), ("surface", "#fefdfc")],
            },
        )

    def test_accepts_only_valid_hex_colors(self):
        payload = {
            "colors": {
                "primary": {"dark": {"color": "red"}, "light": {"color": "#112233"}},
                "error": {"dark": {"color": "#aabbcc; color: red"}},
            }
        }
        self.assertEqual(
            parse_preview_output(json.dumps(payload)),
            {"light": [("primary", "#112233")]},
        )

    def test_rejects_invalid_json_and_missing_palette(self):
        with self.assertRaises(ValueError):
            parse_preview_output("not json")
        with self.assertRaises(ValueError):
            parse_preview_output('{"image": "wallpaper.png"}')

    def test_rejects_palette_with_no_usable_colors(self):
        payload = {"colors": {"primary": {"dark": {"color": "not-a-color"}}}}
        with self.assertRaises(ValueError):
            parse_preview_output(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
