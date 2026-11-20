#!/usr/bin/env python3
"""Standalone settings application for Wallmat.

Run with: python3 src/settings.py

It shares the same GSettings keys (or in-memory fallback) as the main
window, so changes are picked up by Wallmat. Keys that only affect
startup require a restart, which is noted in the UI.
"""

import json
import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Gio, GLib

GLib.set_prgname("wallmat-settings")

sys.path.insert(0, os.path.dirname(__file__))

from window import (
    SCHEMA_ID, ROTATION_INTERVALS, LAYOUT_REGISTRY, _LayoutPreference,
)
from backup_storage import encode_backup, decode_backup
from favorites_storage import decode_favorites, encode_favorites
from tags_storage import decode_tags, encode_tags
from collections_storage import decode_collections, encode_collections
from widgets.thumbnail_loader import CACHE_DIR
from cache_utils import DEFAULT_CACHE_LIMIT_BYTES

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOSTART_FILE = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "autostart", "dev.sakib.Wallmat.Schedule.desktop",
)
CONFIG_DIR = os.path.expanduser("~/.config/wallmat")
FAVORITES_FILE = os.path.join(CONFIG_DIR, "favorites.json")
TAGS_FILE = os.path.join(CONFIG_DIR, "tags.json")
COLLECTIONS_FILE = os.path.join(CONFIG_DIR, "collections.json")

SORT_MODES = (
    ("name", "Name (A–Z)"),
    ("newest", "Newest first"),
    ("oldest", "Oldest first"),
    ("resolution", "Resolution (largest first)"),
    ("random", "Random order"),
    ("folder", "Folder groups"),
)
INTERVAL_LABELS = ("1 minute", "5 minutes", "10 minutes", "30 minutes")
TARGETS = (
    ("desktop", "Desktop background", "Currently the only target Wallmat can apply."),
    ("lock", "Lock screen", "Requires a desktop with a supported lock-screen interface."),
    ("both", "Desktop + lock screen", "Requires a desktop with a supported lock-screen interface."),
)


def _combo(values, selected):
    model = Gtk.StringList.new([label for _key, label in values])
    row = Adw.ComboRow()
    row.set_model(model)
    keys = [key for key, _label in values]
    row.set_selected(keys.index(selected) if selected in keys else 0)
    return row, keys


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback


class WallmatSettingsApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="dev.sakib.Wallmat.Settings")
        self.preference = _LayoutPreference()
        self.window = None

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        self.window = Adw.PreferencesWindow()
        self.window.set_default_size(640, 640)
        self.window.set_title("Wallmat Settings")
        self.window.add(self._browsing_page())
        self.window.add(self._wallpaper_page())
        self.window.add(self._storage_page())
        # GApplication only tracks ApplicationWindow instances; a plain
        # PreferencesWindow needs an explicit hold or run() exits at once.
        self.hold()
        self.window.connect("close-request", self._on_window_close)
        self.window.present()

    def _on_window_close(self, _window):
        self.release()
        self.window = None
        return False

    # -- pages --

    def _browsing_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Browsing")
        page.set_icon_name("view-grid-symbolic")
        group = Adw.PreferencesGroup()
        group.set_title("Startup and filtering")
        group.set_description("Some of these are applied the next time Wallmat starts.")

        layouts = [(key, cls.display_name) for key, cls in LAYOUT_REGISTRY.items()]
        layout_row, self.layout_keys = _combo(
            layouts, self.preference.get_string("selected-layout", "split_screen")
        )
        layout_row.set_title("Startup layout")
        layout_row.connect("notify::selected", self._on_layout)
        group.add(layout_row)

        sort_row, self.sort_keys = _combo(
            SORT_MODES, self.preference.get_string("sort-mode", "name")
        )
        sort_row.set_title("Sort mode")
        sort_row.connect("notify::selected", self._on_sort)
        group.add(sort_row)

        fav_row = Adw.SwitchRow()
        fav_row.set_title("Favorites only")
        fav_row.set_subtitle("Restore the favorites-only filter on startup")
        fav_row.set_active(self.preference.get_boolean("favorites-only", False))
        fav_row.connect("notify::active", self._on_favorites_only)
        group.add(fav_row)

        depth = Adw.SpinRow.new_with_range(0, 20, 1)
        depth.set_title("Scan depth")
        depth.set_subtitle("0 scans all nested folders; restart to rescan")
        depth.set_value(self.preference.get_int("scan-depth", 0))
        depth.connect("notify::value", self._on_scan_depth)
        group.add(depth)

        interval_row, self.interval_keys = _combo(
            list(zip(ROTATION_INTERVALS, INTERVAL_LABELS)),
            self.preference.get_int("auto-rotate-interval", 300),
        )
        interval_row.set_title("Auto-rotation interval")
        interval_row.connect("notify::selected", self._on_interval)
        group.add(interval_row)

        history = Adw.SpinRow.new_with_range(0, 20, 1)
        history.set_title("Random history limit")
        history.set_subtitle("Recently used wallpapers to avoid; 0 disables history")
        history.set_value(self.preference.get_int("random-history-limit", 5))
        history.connect("notify::value", self._on_history)
        group.add(history)

        page.add(group)

        display = Adw.PreferencesGroup()
        display.set_title("Window backdrop")
        display.set_description(
            "The app never uses a solid background. Seamless mode additionally "
            "hides the controls; Ctrl+Shift+S toggles it in the app."
        )
        seamless = Adw.SwitchRow()
        seamless.set_title("Seamless wallpaper view")
        seamless.set_subtitle("Hide all controls and use a transparent or blurred backdrop")
        seamless.set_active(self.preference.get_boolean("seamless-mode", False))
        seamless.connect("notify::active", self._on_seamless)
        display.add(seamless)

        backdrops = (("transparent", "Transparent"), ("blurred", "Blurred"))
        backdrop_row, self.backdrop_keys = _combo(
            backdrops, self.preference.get_string("seamless-backdrop", "blurred")
        )
        backdrop_row.set_title("Backdrop")
        backdrop_row.connect("notify::selected", self._on_seamless_backdrop)
        self.backdrop_row = backdrop_row
        display.add(backdrop_row)

        page.add(display)

        service = Adw.PreferencesGroup()
        service.set_title("Background service")
        service.set_description(
            "Apply the active schedule even when Wallmat is closed."
        )
        background = Adw.SwitchRow()
        background.set_title("Run schedules in background")
        background.set_subtitle("Start the schedule service at login")
        background.set_active(os.path.exists(AUTOSTART_FILE))
        background.connect("notify::active", self._on_background_service)
        service.add(background)
        page.add(service)
        return page

    def _wallpaper_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Wallpaper")
        page.set_icon_name("image-x-generic-symbolic")
        group = Adw.PreferencesGroup()
        group.set_title("Sources and application")
        group.set_description("Defaults used when Wallmat is launched without options.")

        folder = self.preference.get_string("last-wallpaper-folder", "")
        folder_row = Adw.ActionRow()
        folder_row.set_title("Default wallpaper folder")
        folder_row.set_subtitle(folder or "None set — /usr/share/backgrounds is used")
        choose = Gtk.Button(label="Choose…")
        choose.set_valign(Gtk.Align.CENTER)
        choose.connect("clicked", self._on_choose_folder, folder_row)
        folder_row.add_suffix(choose)
        group.add(folder_row)

        args = Adw.EntryRow()
        args.set_title("Matugen arguments")
        args.set_text(self.preference.get_string("matugen-args",
                                                 "--type scheme-smart --mode dark"))
        args.connect("changed", self._on_matugen_args)
        group.add(args)

        targets = [(key, label) for key, label, _hint in TARGETS]
        target_row, self.target_keys = _combo(
            targets, self.preference.get_string("wallpaper-target", "desktop")
        )
        target_row.set_title("Apply wallpaper to")
        target_row.connect("notify::selected", self._on_target)
        group.add(target_row)

        hint = Adw.ActionRow()
        hint.set_title("Lock-screen support")
        hint.set_subtitle(
            "Only the desktop background is applied today. Other targets need a "
            "desktop service that Wallmat does not use yet."
        )
        hint.add_css_class("dim-label")
        group.add(hint)

        page.add(group)
        return page

    def _storage_page(self):
        page = Adw.PreferencesPage()
        page.set_title("Storage")
        page.set_icon_name("drive-harddisk-symbolic")

        data_group = Adw.PreferencesGroup()
        data_group.set_title("User data")
        for title, path in (
            ("Favorites", FAVORITES_FILE),
            ("Tags", TAGS_FILE),
            ("Collections", COLLECTIONS_FILE),
        ):
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(path)
            data_group.add(row)
        page.add(data_group)

        backup_group = Adw.PreferencesGroup()
        backup_group.set_title("Backup and restore")
        export_row = Adw.ActionRow()
        export_row.set_title("Export backup…")
        export_row.set_subtitle("Save favorites, tags, collections and preferences")
        export_btn = Gtk.Button(label="Export")
        export_btn.set_valign(Gtk.Align.CENTER)
        export_btn.connect("clicked", self._on_export_backup)
        export_row.add_suffix(export_btn)
        backup_group.add(export_row)

        restore_row = Adw.ActionRow()
        restore_row.set_title("Restore backup…")
        restore_row.set_subtitle("Replace current data after validation")
        restore_btn = Gtk.Button(label="Restore")
        restore_btn.set_valign(Gtk.Align.CENTER)
        restore_btn.connect("clicked", self._on_restore_backup)
        restore_row.add_suffix(restore_btn)
        backup_group.add(restore_row)
        page.add(backup_group)

        cache_group = Adw.PreferencesGroup()
        cache_group.set_title("Thumbnail cache")
        cache_group.set_description(CACHE_DIR)
        limit = Adw.SpinRow.new_with_range(64, 4096, 64)
        limit.set_title("Cache size limit (MiB)")
        limit.set_value(self.preference.get_int("thumbnail-cache-limit-mb", 512))
        limit.connect("notify::value", self._on_cache_limit)
        cache_group.add(limit)

        clear_row = Adw.ActionRow()
        clear_row.set_title("Clear thumbnail cache")
        clear_row.set_subtitle("Remove cached thumbnails; they will be regenerated")
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._on_clear_cache)
        clear_row.add_suffix(clear_btn)
        cache_group.add(clear_row)
        page.add(cache_group)

        return page

    # -- callbacks --

    def _on_layout(self, row, _pspec):
        self.preference.set_string("selected-layout",
                                   self.layout_keys[row.get_selected()])

    def _on_sort(self, row, _pspec):
        self.preference.set_string("sort-mode", self.sort_keys[row.get_selected()])

    def _on_favorites_only(self, row, _pspec):
        self.preference.set_boolean("favorites-only", row.get_active())

    def _on_scan_depth(self, row, _pspec):
        self.preference.set_int("scan-depth", int(row.get_value()))

    def _on_interval(self, row, _pspec):
        self.preference.set_int("auto-rotate-interval",
                                self.interval_keys[row.get_selected()])

    def _on_history(self, row, _pspec):
        self.preference.set_int("random-history-limit", int(row.get_value()))

    def _on_background_service(self, row, _pspec):
        if row.get_active():
            os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
            with open(AUTOSTART_FILE, "w", encoding="utf-8") as handle:
                handle.write(
                    "[Desktop Entry]\nType=Application\n"
                    "Name=Wallmat Schedule Service\n"
                    f"Exec={sys.executable} {SOURCE_DIR}/schedule_daemon.py\n"
                    "TryExec=python3\nTerminal=false\nNoDisplay=true\n"
                    "X-GNOME-Autostart-enabled=true\n"
                )
            already_running = subprocess.run(
                ["pgrep", "-f", "schedule_daemon.py"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
            ).returncode == 0
            if not already_running:
                try:
                    subprocess.Popen(
                        [sys.executable, f"{SOURCE_DIR}/schedule_daemon.py"],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except OSError:
                    pass
        else:
            try:
                os.remove(AUTOSTART_FILE)
            except OSError:
                pass

    def _on_seamless(self, row, _pspec):
        self.preference.set_boolean("seamless-mode", row.get_active())

    def _on_seamless_backdrop(self, row, _pspec):
        self.preference.set_string("seamless-backdrop",
                                   self.backdrop_keys[row.get_selected()])

    def _on_choose_folder(self, _button, row):
        dialog = Gtk.FileDialog()
        dialog.set_title("Default wallpaper folder")
        initial = row.get_subtitle() or ""
        if initial and os.path.isdir(initial):
            dialog.set_initial_folder(Gio.File.new_for_path(initial))

        def done(source, result):
            try:
                folder = source.select_folder_finish(result)
            except GLib.Error:
                return
            path = folder.get_path()
            self.preference.set_string("last-wallpaper-folder", path)
            row.set_subtitle(path)

        dialog.select_folder(self.window, None, done)

    def _on_matugen_args(self, entry):
        self.preference.set_string("matugen-args", entry.get_text())

    def _on_target(self, row, _pspec):
        self.preference.set_string("wallpaper-target",
                                   self.target_keys[row.get_selected()])

    def _on_cache_limit(self, row, _pspec):
        self.preference.set_int("thumbnail-cache-limit-mb", int(row.get_value()))

    def _on_clear_cache(self, _button):
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Clear thumbnail cache?",
            body="Cached thumbnails will be removed and regenerated on demand.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("clear", "Clear")
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._clear_cache_response)
        dialog.present()

    def _clear_cache_response(self, dialog, response):
        dialog.destroy()
        if response != "clear":
            return
        removed = 0
        try:
            for name in os.listdir(CACHE_DIR):
                path = os.path.join(CACHE_DIR, name)
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
        except OSError:
            pass
        self._toast(f"Removed {removed} cached thumbnail(s)")

    def _on_export_backup(self, _button):
        dialog = Gtk.FileDialog()
        dialog.set_title("Export Wallmat backup")
        dialog.set_initial_name("wallmat-backup.json")

        def done(source, result):
            try:
                file = source.save_finish(result)
            except GLib.Error:
                return
            root = self.preference.get_string("last-wallpaper-folder", "")
            favorites = decode_favorites(_read_json(FAVORITES_FILE, []), root)
            tags = decode_tags(_read_json(TAGS_FILE, {}), root)
            collections = decode_collections(_read_json(COLLECTIONS_FILE, {}))
            data = encode_backup(favorites, root, self.preference.export_values(),
                                 tags, collections)
            try:
                with open(file.get_path(), "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2, ensure_ascii=False)
                self._toast("Backup exported")
            except OSError as error:
                self._toast(f"Could not write backup: {error}")

        dialog.save(self.window, None, done)

    def _on_restore_backup(self, _button):
        dialog = Gtk.FileDialog()
        dialog.set_title("Restore Wallmat backup")

        def done(source, result):
            try:
                file = source.open_finish(result)
            except GLib.Error:
                return
            try:
                with open(file.get_path(), "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                root = self.preference.get_string("last-wallpaper-folder", "")
                restored = decode_backup(data, root)
            except (OSError, ValueError) as error:
                self._toast(f"Invalid backup: {error}")
                return
            _atomic_write(FAVORITES_FILE,
                          encode_favorites(restored["favorites"], root))
            _atomic_write(TAGS_FILE, encode_tags(restored["tags"] or {}, root))
            _atomic_write(COLLECTIONS_FILE,
                          encode_collections(restored["collections"] or {}))
            self.preference.import_values(restored["preferences"])
            self._toast("Backup restored — restart Wallmat to apply preferences")

        dialog.open(self.window, None, done)

    def _toast(self, message):
        if hasattr(self.window, "add_toast"):
            self.window.add_toast(Adw.Toast.new(message))


def main():
    app = WallmatSettingsApp()
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
