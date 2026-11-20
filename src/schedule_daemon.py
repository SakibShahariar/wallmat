#!/usr/bin/env python3
"""Background service for time-based wallpaper schedules.

Runs independently of the main window: checks the active local-time period
once a minute and applies a wallpaper when the period changes. Autostart is
installed by install.sh / Wallmat Settings.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio, GLib, GdkPixbuf

from window import (
    SCHEMA_ID, LAST_FOLDER_KEY, SCAN_DEPTH_KEY, _LayoutPreference,
)
from collections_storage import decode_collections
from schedule import parse_schedule, active_period, period_candidates
from portal_wallpaper import request_wallpaper
from random_selection import choose_next

CONFIG_DIR = os.path.expanduser("~/.config/wallmat")
COLLECTIONS_FILE = os.path.join(CONFIG_DIR, "collections.json")
STATE_FILE = os.path.join(CONFIG_DIR, "schedule-state.json")
CHECK_INTERVAL_MS = 60_000


def supported_extensions():
    safe = {".png", ".jpg", ".jpeg", ".webp"}
    extensions = set()
    for image_format in GdkPixbuf.Pixbuf.get_formats():
        if image_format.is_disabled():
            continue
        for extension in image_format.get_extensions():
            if f".{extension.lower()}" in safe:
                extensions.add(f".{extension.lower()}")
    return extensions


def load_collections(root):
    try:
        with open(COLLECTIONS_FILE, "r", encoding="utf-8") as handle:
            return decode_collections(json.load(handle), root)
    except (OSError, ValueError):
        return {}


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        temporary = STATE_FILE + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(temporary, STATE_FILE)
    except OSError:
        pass


def apply_wallpaper(path):
    def fallback():
        try:
            settings = Gio.Settings.new("org.gnome.desktop.background")
            uri = GLib.filename_to_uri(path)
            if "picture-uri" in settings.list_keys():
                settings.set_string("picture-uri", uri)
            if "picture-uri-dark" in settings.list_keys():
                settings.set_string("picture-uri-dark", uri)
        except GLib.Error:
            pass

    if os.environ.get("WAYLAND_DISPLAY") or \
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        request_wallpaper(path, lambda result, _message: None if result else fallback())
    else:
        fallback()


def check_once(preference):
    try:
        periods = parse_schedule(
            preference.get_string("rotation-schedule", "[]")
        )
    except ValueError:
        return
    if not periods:
        return
    from datetime import datetime
    now = datetime.now().astimezone()
    active = active_period(periods, now.hour * 60 + now.minute)
    if active is None:
        return
    state = load_state()
    if state.get("period") == active.name and state.get("schedule") == \
            preference.get_string("rotation-schedule", "[]"):
        return
    root = preference.get_string(LAST_FOLDER_KEY, "")
    candidates = period_candidates(
        active, load_collections(root), [], root,
        supported_extensions(),
        preference.get_int(SCAN_DEPTH_KEY, 0),
    )
    if not candidates:
        return
    chosen, _history = choose_next(candidates, [], 0)
    if chosen is None:
        return
    apply_wallpaper(chosen)
    save_state({
        "period": active.name,
        "schedule": preference.get_string("rotation-schedule", "[]"),
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                        help="apply the current period once and exit")
    args = parser.parse_args()
    preference = _LayoutPreference()
    if args.once:
        check_once(preference)
        return 0
    GLib.timeout_add(1000, lambda: (check_once(preference), True)[1])
    GLib.timeout_add(CHECK_INTERVAL_MS, lambda: (check_once(preference), True)[1])
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
