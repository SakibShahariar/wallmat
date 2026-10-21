#!/usr/bin/env python3
"""
Entry point for the multi-layout wallpaper chooser prototype.

Usage:
    python3 main.py /path/to/wallpaper/folder
    python3 main.py /path/to/wallpaper/folder --layout infinite_ribbon
    (defaults to /usr/share/backgrounds if no directory given)

--plain: picker-only contract for the matugen.fish pipeline. All
feedback prints are silenced; on selection the app prints the bare
wallpaper path to stdout (the ONLY stdout line) and exits — a drop-in
replacement for wallpicker.py.

Layouts are built lazily — each one only gets constructed the first
time you switch to it. You can choose a layout with the compact in-app
selector or use --layout to launch directly into one. The CLI option
also sizes the window for that layout up front (see LAYOUT_WINDOW_SIZES
in window.py), since GTK/Wayland generally won't let an app resize its
own window after it's first shown.
Valid ids: split_screen, stacked_deck, infinite_ribbon, masonry_grid,
glassmorphism, parallax_gallery, radial_fan, cylindrical_ring.
"""

import sys
import os
import argparse
import shlex

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

sys.path.insert(0, os.path.dirname(__file__))
from window import WallpaperChooserWindow, LAYOUT_REGISTRY


class WallpaperChooserApp(Adw.Application):
    def __init__(
        self, wallpaper_dir: str, initial_layout_id: str | None,
        plain: bool = False, matugen_args: list[str] | None = None,
    ):
        super().__init__(application_id="dev.sakib.Wallmat")
        self.wallpaper_dir = wallpaper_dir
        self.initial_layout_id = initial_layout_id
        self.plain = plain
        self.matugen_args = matugen_args or ["--type", "scheme-smart", "--mode", "dark"]

    def do_activate(self):
        win = WallpaperChooserWindow(
            self, self.wallpaper_dir, self.initial_layout_id,
            plain=self.plain, matugen_args=self.matugen_args,
        )
        win.present()


def main():
    parser = argparse.ArgumentParser(description="Wallpaper Chooser Prototype")
    parser.add_argument(
        "wallpaper_dir", nargs="?", default="/usr/share/backgrounds",
        help="Directory of wallpaper images to load"
    )
    parser.add_argument(
        "--layout", default=None, choices=sorted(LAYOUT_REGISTRY.keys()),
        help="Launch directly into this layout (also sizes the window for it)"
    )
    parser.add_argument(
        "--plain", action="store_true",
        help="Picker-only mode: silence all feedback prints, output the bare "
             "wallpaper path on selection and exit"
    )
    parser.add_argument(
        "--matugen-args", default="--type scheme-smart --mode dark",
        help="Arguments passed to matugen after 'image PATH' (default: "
             "'--type scheme-smart --mode dark'); parsed without a shell"
    )
    args = parser.parse_args()

    app = WallpaperChooserApp(
        args.wallpaper_dir, args.layout, plain=args.plain,
        matugen_args=shlex.split(args.matugen_args),
    )
    app.run([])


if __name__ == "__main__":
    main()
