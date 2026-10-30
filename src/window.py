"""
WallpaperChooserWindow: hosts a Gtk.Stack of lazily-built layouts. Layouts
can be switched in-app with the compact selector below the wallpaper view,
or selected at launch with --layout. The active layout is persisted through
GSettings when the schema is installed; otherwise an in-memory fallback is
used for the current run.

NOTE on the GSettings schema: this uses a schema id
(dev.sakib.Wallmat) that is NOT installed on the
system by default. GSettings requires a compiled schema file to exist
under a glib schema directory before Gio.Settings.new() will succeed — if
you see a GLib.Error about an unknown schema when running this, that's why.
The repository includes data/dev.sakib.Wallmat.gschema.xml and README install
instructions. If the schema is not installed, _LayoutPreference falls back
to an in-memory value, so the app still runs but the preference is not
persisted across restarts.
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import random

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, GdkPixbuf

from layouts.split_screen import SplitScreenLayout
from layouts.stacked_deck import StackedDeckLayout
from layouts.cylindrical_ring import CylindricalRingLayout
from layouts.glassmorphism import GlassmorphismLayout
from layouts.infinite_ribbon import InfiniteRibbonLayout
from layouts.parallax_gallery import ParallaxGalleryLayout
from layouts.masonry_grid import MasonryGridLayout
from layouts.radial_fan import RadialFanLayout

from widgets.gsk_utils import register_focus_colors
from announce import say, set_quiet
from random_selection import (
    MAX_RANDOM_HISTORY,
    choose_next,
    shuffle_with_recent_last,
)
from wallpaper_scan import MAX_SCAN_DEPTH, scan_wallpapers
from wallpaper_sort import sort_by_resolution
from wallpaper_history import (
    MAX_APPLIED_HISTORY,
    append_applied,
    for_collection,
)
from favorites_storage import decode_favorites, encode_favorites
from plain_mode import SUCCESS, CANCELLED, SCAN_FAILED

SCHEMA_ID = "dev.sakib.Wallmat"
SETTINGS_KEY = "selected-layout"
FILTER_KEY = "last-filter"
SORT_KEY = "sort-mode"
FAVORITES_ONLY_KEY = "favorites-only"
SELECTED_PATH_KEY = "selected-wallpaper"
RECENT_PATHS_KEY = "recent-wallpapers"
AUTO_ROTATE_INTERVAL_KEY = "auto-rotate-interval"
RECENT_RANDOM_PATHS_KEY = "recent-random-wallpapers"
RANDOM_HISTORY_LIMIT_KEY = "random-history-limit"
ROTATION_INTERVALS = (60, 300, 600, 1800)
DEFAULT_ROTATION_INTERVAL = 300
DEFAULT_RANDOM_HISTORY_LIMIT = 5
SCAN_DEPTH_KEY = "scan-depth"
DEFAULT_SCAN_DEPTH = 0
APPLIED_HISTORY_KEY = "applied-wallpaper-history"
MAX_RECENT_WALLPAPERS = 8
DEFAULT_LAYOUT_ID = "split_screen"

# Keep very large wallpaper collections from monopolizing startup. The scan
# stops after this many supported images and reports that the result is capped.
MAX_WALLPAPERS = 10_000

LAYOUT_REGISTRY = {
    "split_screen": SplitScreenLayout,
    "stacked_deck": StackedDeckLayout,
    "infinite_ribbon": InfiniteRibbonLayout,
    "masonry_grid": MasonryGridLayout,
    "glassmorphism": GlassmorphismLayout,
    "parallax_gallery": ParallaxGalleryLayout,
    "radial_fan": RadialFanLayout,
    "cylindrical_ring": CylindricalRingLayout,
}

# Preferred window size per layout, used when launching directly into a
# layout via `python3 main.py <dir> --layout <id>`. Compact/short layouts
# (single carousel row) don't need as much vertical room as grid/split
# layouts — this only takes effect at window construction (before first
# show), since GTK/Wayland generally won't let an app resize itself after
# that without user interaction.
LAYOUT_WINDOW_SIZES = {
    "split_screen": (1000, 600),
    # Deck widget is 560x340 + 40px margins (600x380), plus a hint label
    # and button below it — natural content is roughly 600x480. Was
    # previously (1000, 600), leaving a large empty margin around a
    # small centered deck since the deck's root Box doesn't expand to
    # fill leftover space (it's deliberately centered, not stretched).
    "stacked_deck": (680, 540),
    "infinite_ribbon": (1000, 420),
    "masonry_grid": (1000, 700),
    "glassmorphism": (1000, 500),
    "parallax_gallery": (1000, 500),
    "radial_fan": (1000, 600),
    "cylindrical_ring": (1000, 500),
}
DEFAULT_WINDOW_SIZE = (1000, 600)


class _LayoutPreference:
    """Wraps Gio.Settings, falling back to an in-memory value if the
    GSettings schema isn't installed (see module docstring)."""

    def __init__(self):
        self._settings = None
        self._memory_values = {
            SETTINGS_KEY: DEFAULT_LAYOUT_ID,
            FILTER_KEY: "",
            SORT_KEY: "name",
            FAVORITES_ONLY_KEY: False,
            SELECTED_PATH_KEY: "",
            RECENT_PATHS_KEY: [],
            AUTO_ROTATE_INTERVAL_KEY: DEFAULT_ROTATION_INTERVAL,
            RECENT_RANDOM_PATHS_KEY: [],
            RANDOM_HISTORY_LIMIT_KEY: DEFAULT_RANDOM_HISTORY_LIMIT,
            SCAN_DEPTH_KEY: DEFAULT_SCAN_DEPTH,
            APPLIED_HISTORY_KEY: [],
        }
        try:
            schema_source = Gio.SettingsSchemaSource.get_default()
            if schema_source and schema_source.lookup(SCHEMA_ID, True):
                self._settings = Gio.Settings.new(SCHEMA_ID)
        except GLib.Error:
            self._settings = None

    def _has_key(self, key: str) -> bool:
        return (
            self._settings is not None
            and self._settings.get_settings_schema().has_key(key)
        )

    def get_string(self, key: str, default: str) -> str:
        if self._has_key(key):
            return self._settings.get_string(key)
        return self._memory_values.get(key, default)

    def set_string(self, key: str, value: str):
        if self._has_key(key):
            self._settings.set_string(key, value)
        else:
            self._memory_values[key] = value

    def get_strv(self, key: str) -> list[str]:
        if self._has_key(key):
            return list(self._settings.get_strv(key))
        value = self._memory_values.get(key, [])
        return list(value) if isinstance(value, list) else []

    def set_strv(self, key: str, value: list[str]):
        if self._has_key(key):
            self._settings.set_strv(key, value)
        else:
            self._memory_values[key] = list(value)

    def get_boolean(self, key: str, default: bool = False) -> bool:
        if self._has_key(key):
            return self._settings.get_boolean(key)
        return self._memory_values.get(key, default)

    def set_boolean(self, key: str, value: bool):
        if self._has_key(key):
            self._settings.set_boolean(key, value)
        else:
            self._memory_values[key] = value

    def get_int(self, key: str, default: int = 0) -> int:
        if self._has_key(key):
            return self._settings.get_int(key)
        return self._memory_values.get(key, default)

    def set_int(self, key: str, value: int):
        if self._has_key(key):
            self._settings.set_int(key, value)
        else:
            self._memory_values[key] = value

    def get(self) -> str:
        return self.get_string(SETTINGS_KEY, DEFAULT_LAYOUT_ID)

    @property
    def persistent(self) -> bool:
        return self._settings is not None

    def set(self, layout_id: str):
        self.set_string(SETTINGS_KEY, layout_id)


class WallpaperChooserWindow(Adw.ApplicationWindow):
    def __init__(self, app, wallpaper_dir: str, initial_layout_id: str | None = None,
                 plain: bool = False, matugen_args: list[str] | None = None):
        super().__init__(application=app, title="Wallpaper Chooser")
        self._plain = plain
        if plain:
            self.get_application().plain_exit_code = CANCELLED
        self._matugen_args = list(
            matugen_args or ["--type", "scheme-smart", "--mode", "dark"]
        )
        self._selected_path: str | None = None
        self._rotation_source_id: int | None = None
        self._rotation_history: list[str] = []
        self._rotation_history_index = -1
        self._history_navigation = False
        self._rotation_interval_seconds = 300
        self.connect("close-request", self._on_window_close_request)
        self._wallpaper_dir = os.path.abspath(wallpaper_dir)
        config_dir = os.path.expanduser("~/.config/wallmat")
        self._favorites_file = os.path.join(config_dir, "favorites.json")
        self._favorites_export_file = os.path.join(config_dir, "favorites.txt")
        self._favorites: set[str] = set()
        self._favorites_load_warning: str | None = None
        self._favorites_write_blocked = False
        try:
            with open(self._favorites_file, "r", encoding="utf-8") as handle:
                saved_favorites = json.load(handle)
            self._favorites = decode_favorites(
                saved_favorites, self._wallpaper_dir
            )
        except FileNotFoundError:
            # A first launch has no favorites file yet; this is not an error.
            pass
        except (OSError, json.JSONDecodeError, ValueError) as error:
            try:
                backup_path = self._backup_corrupt_favorites()
                self._favorites_load_warning = (
                    f"Wallmat could not load favorites ({error}). The original "
                    f"file was preserved at:\n{backup_path}\n\n"
                    "Wallmat will continue with an empty favorites list. The "
                    "backup will remain available if you need to recover it."
                )
            except OSError as backup_error:
                self._favorites_write_blocked = True
                self._favorites_load_warning = (
                    f"Wallmat could not load favorites ({error}) and could not "
                    f"create a recovery backup ({backup_error}). The original "
                    "file has not been replaced, and saving favorites is "
                    "disabled for this session to protect it. Make a manual "
                    "copy or fix the file permissions before trying again."
                )
        if plain:
            # stdout must carry ONLY the final selected path (the
            # matugen.fish pipeline captures it via fish command
            # substitution). Silence all announce() feedback lines.
            set_quiet(True)

        # If a layout was explicitly requested via --layout, size the
        # window for that layout up front; otherwise use the generic
        # default. Only affects the window's INITIAL size (see note
        # above on LAYOUT_WINDOW_SIZES about why this can't reliably
        # change later).
        if initial_layout_id in LAYOUT_WINDOW_SIZES:
            self.set_default_size(*LAYOUT_WINDOW_SIZES[initial_layout_id])
        else:
            self.set_default_size(*DEFAULT_WINDOW_SIZE)

        # Escape closes the window.
        escape_controller = Gtk.EventControllerKey()
        escape_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(escape_controller)

        # Named colors (wc-focus-ring etc.) need a Gdk.Display before
        # they can be registered — do it once the window is realized.
        # User gtk.css overrides these at USER priority.
        self.connect("realize", self._register_focus_colors)

        self._preference = _LayoutPreference()
        saved_rotation_interval = self._preference.get_int(
            AUTO_ROTATE_INTERVAL_KEY, DEFAULT_ROTATION_INTERVAL
        )
        if saved_rotation_interval not in ROTATION_INTERVALS:
            saved_rotation_interval = DEFAULT_ROTATION_INTERVAL
        self._rotation_interval_seconds = saved_rotation_interval
        self._paths: list[str] = []
        self._all_paths: list[str] = []
        self._layouts: dict[str, object] = {}
        self._stale_layouts: set[str] = set()
        self._current_layout_id: str | None = None

        toolbar_view = Adw.ToolbarView()

        # Keep the window chrome-free as requested. Layouts remain
        # switchable through the compact selector below the wallpaper view;
        # --layout can still choose the initial layout at launch. Escape
        # closes the window. Without a title bar, window movement and
        # minimize/maximize depend on the window manager's shortcuts.
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)

        # Ctrl+F reveals a lightweight filename filter without permanently
        # taking space away from the wallpaper layouts.
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Filter wallpapers by filename or folder…")
        self.search_entry.set_margin_start(12)
        self.search_entry.set_margin_end(12)
        self.search_entry.set_margin_top(8)
        self.search_entry.set_margin_bottom(8)
        self.search_entry.set_visible(False)
        self.search_entry.connect("search-changed", self._on_search_changed)

        # Restore the user's browsing filters when GSettings is available.
        self._favorites_only = (
            self._preference.get_boolean(FAVORITES_ONLY_KEY)
            if not plain else False
        )
        saved_sort_mode = (
            self._preference.get_string(SORT_KEY, "name")
            if not plain else "name"
        )
        if saved_sort_mode not in (
            "name", "newest", "oldest", "resolution", "random", "folder"
        ):
            saved_sort_mode = "name"
        self._sort_mode = saved_sort_mode
        self._random_order: list[str] = []
        self._resolution_cache: dict[str, tuple[tuple[int, int], tuple[int, int] | None]] = {}
        self.sort_selector = Gtk.DropDown.new_from_strings([
            "Name (A–Z)", "Newest first", "Oldest first",
            "Resolution (largest first)", "Random order", "Folder groups"
        ])
        self.sort_selector.set_selected(
            ("name", "newest", "oldest", "resolution", "random", "folder").index(
                self._sort_mode
            )
        )
        self.sort_selector.set_tooltip_text("Sort wallpapers")
        self.sort_selector.set_margin_start(12)
        self.sort_selector.set_margin_end(12)
        self.sort_selector.set_margin_bottom(6)
        self.sort_selector.set_visible(not self._plain)
        self.sort_selector.connect("notify::selected", self._on_sort_selected)

        self.favorites_filter = Gtk.CheckButton(label="Favorites only")
        self.favorites_filter.set_active(self._favorites_only)
        self.favorites_filter.set_margin_start(12)
        self.favorites_filter.set_margin_end(12)
        self.favorites_filter.set_margin_bottom(6)
        self.favorites_filter.set_visible(not self._plain)
        self.favorites_filter.connect("toggled", self._on_favorites_filter_toggled)

        # Empty-state message covers both an empty directory and a filter
        # with no matching filenames.
        content_overlay = Gtk.Overlay()
        content_overlay.set_child(self.stack)
        self._empty_state = Adw.StatusPage()
        self._empty_state.set_icon_name("folder-open-symbolic")
        self._empty_state.set_title("No wallpapers found")
        self._empty_state.set_description(
            "This folder has no supported wallpaper images."
        )
        self._empty_state.set_visible(False)
        content_overlay.add_overlay(self._empty_state)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.append(self.search_entry)
        content.append(self.sort_selector)
        content.append(self.favorites_filter)

        recent_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        recent_row.set_halign(Gtk.Align.CENTER)
        recent_row.set_margin_start(12)
        recent_row.set_margin_end(12)
        recent_row.set_margin_bottom(6)
        recent_label = Gtk.Label(label="Recent")
        recent_row.append(recent_label)
        self._recent_paths: list[str] = []
        self._recent_selector = Gtk.DropDown.new_from_strings(["No recent wallpapers"])
        self._recent_selector.set_sensitive(False)
        self._recent_selector.set_tooltip_text("Reopen a recently selected wallpaper")
        self._recent_selector.connect("notify::selected", self._on_recent_selected)
        recent_row.append(self._recent_selector)
        recent_row.set_visible(not plain)
        content.append(recent_row)

        self._metadata_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        self._metadata_row.set_margin_start(16)
        self._metadata_row.set_margin_end(16)
        self._metadata_row.set_margin_bottom(8)
        self._metadata_label = Gtk.Label()
        self._metadata_label.set_wrap(True)
        self._metadata_label.set_xalign(0.0)
        self._metadata_label.set_hexpand(True)
        self._metadata_label.add_css_class("dim-label")
        self._metadata_label.set_selectable(True)
        self._metadata_row.append(self._metadata_label)
        copy_metadata_button = Gtk.Button(label="Copy details")
        copy_metadata_button.set_tooltip_text("Copy wallpaper metadata and path")
        copy_metadata_button.connect("clicked", self._on_copy_metadata)
        self._metadata_row.append(copy_metadata_button)
        hide_metadata_button = Gtk.Button(label="Hide")
        hide_metadata_button.set_tooltip_text("Hide wallpaper details")
        hide_metadata_button.connect("clicked", self._on_hide_metadata)
        self._metadata_row.append(hide_metadata_button)
        self._metadata_row.set_visible(False)
        content.append(self._metadata_row)

        self._settings_notice = Gtk.Label(
            label=(
                "Wallmat preferences will not persist because its GSettings "
                "schema is unavailable. See schema installation instructions "
                "in README.md."
            )
        )
        self._settings_notice.set_wrap(True)
        self._settings_notice.set_xalign(0.5)
        self._settings_notice.set_margin_start(16)
        self._settings_notice.set_margin_end(16)
        self._settings_notice.set_margin_bottom(8)
        self._settings_notice.add_css_class("dim-label")
        self._settings_notice.set_visible(not self._preference.persistent and not plain)
        content.append(self._settings_notice)

        self._scan_limit_notice = Gtk.Label(
            label=(
                f"Showing the first {MAX_WALLPAPERS:,} wallpapers. "
                "Some images were omitted; choose a narrower folder to browse them."
            )
        )
        self._scan_limit_notice.set_wrap(True)
        self._scan_limit_notice.set_xalign(0.5)
        self._scan_limit_notice.set_margin_start(16)
        self._scan_limit_notice.set_margin_end(16)
        self._scan_limit_notice.set_margin_bottom(8)
        self._scan_limit_notice.add_css_class("info")
        self._scan_limit_notice.set_visible(False)
        content.append(self._scan_limit_notice)

        self._scan_error_notice = Gtk.Label()
        self._scan_error_notice.set_wrap(True)
        self._scan_error_notice.set_xalign(0.0)
        self._scan_error_notice.set_margin_start(16)
        self._scan_error_notice.set_margin_end(16)
        self._scan_error_notice.set_margin_bottom(8)
        self._scan_error_notice.add_css_class("warning")
        self._scan_error_notice.set_visible(False)
        content.append(self._scan_error_notice)
        content.append(content_overlay)

        # FlowBox wraps the action controls when the window is narrow or
        # text scaling increases, instead of clipping a fixed horizontal row.
        action_row = Gtk.FlowBox()
        action_row.set_selection_mode(Gtk.SelectionMode.NONE)
        action_row.set_homogeneous(False)
        action_row.set_max_children_per_line(4)
        action_row.set_min_children_per_line(1)
        action_row.set_row_spacing(8)
        action_row.set_column_spacing(8)
        action_row.set_hexpand(True)
        action_row.set_halign(Gtk.Align.FILL)
        action_row.set_margin_top(8)
        action_row.set_margin_bottom(10)

        # Keep layout selection available without restoring a header bar.
        layout_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        layout_row.set_halign(Gtk.Align.CENTER)
        layout_row.set_margin_top(8)
        self._layout_ids = list(LAYOUT_REGISTRY)
        self._layout_labels = [
            "Split-Screen Preview",
            "Stacked Deck",
            "Infinite Ribbon",
            "Masonry Grid",
            "Glassmorphism",
            "Parallax Gallery",
            "Radial Fan",
            "Cylindrical Ring",
        ]
        self.layout_selector = Gtk.DropDown.new_from_strings(self._layout_labels)
        self.layout_selector.set_tooltip_text("Switch wallpaper layout")
        self.layout_selector.connect(
            "notify::selected", self._on_layout_selected
        )
        layout_row.append(self.layout_selector)
        self.shortcuts_button = Gtk.Button(label="Shortcuts")
        self.shortcuts_button.set_tooltip_text("Show keyboard shortcuts")
        self.shortcuts_button.connect("clicked", self._show_shortcuts)
        layout_row.append(self.shortcuts_button)
        content.append(layout_row)

        self.set_wallpaper_button = Gtk.Button(label="Set as wallpaper")
        self.set_wallpaper_button.set_sensitive(False)
        self.set_wallpaper_button.connect("clicked", self._on_apply_wallpaper)
        self.preview_button = Gtk.Button(label="Preview")
        self.preview_button.set_tooltip_text(
            "Open a large preview; use the zoom control and scroll to inspect details"
        )
        self.preview_button.set_sensitive(False)
        self.preview_button.connect("clicked", self._on_open_preview)
        self.apply_matugen_button = Gtk.Button(label="Apply wallpaper + Matugen")
        self.apply_matugen_button.add_css_class("suggested-action")
        self.apply_matugen_button.set_sensitive(False)
        self.apply_matugen_button.connect("clicked", self._on_apply_matugen)
        self.favorite_button = Gtk.Button(label="Add to favorites")
        self.favorite_button.set_sensitive(False)
        self.favorite_button.connect("clicked", self._on_toggle_favorite)
        self.export_favorites_button = Gtk.Button(label="Export favorites")
        self.export_favorites_button.connect("clicked", self._on_export_favorites)
        self.surprise_button = Gtk.Button(label="Surprise me")
        self.surprise_button.set_tooltip_text(
            "Choose and immediately apply a random wallpaper from the current filtered results"
        )
        self.surprise_button.connect("clicked", self._on_surprise_me)
        for action_button in (
            self.preview_button,
            self.set_wallpaper_button,
            self.apply_matugen_button,
            self.favorite_button,
            self.export_favorites_button,
            self.surprise_button,
        ):
            action_row.insert(action_button, -1)
        # Plain mode is a path picker for shell pipelines, not a desktop
        # wallpaper manager; keep unrelated apply/favorites actions hidden.
        action_row.set_visible(not self._plain)
        content.append(action_row)

        rotation_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        rotation_row.set_halign(Gtk.Align.CENTER)
        rotation_row.set_margin_bottom(8)
        self.auto_rotate_toggle = Gtk.CheckButton(label="Auto-rotate")
        self.auto_rotate_toggle.set_tooltip_text(
            "Apply a random wallpaper from the current filtered results at an interval"
        )
        self.auto_rotate_toggle.connect("toggled", self._on_auto_rotate_toggled)
        rotation_row.append(self.auto_rotate_toggle)
        self.rotation_interval = Gtk.DropDown.new_from_strings(
            ["1 minute", "5 minutes", "10 minutes", "30 minutes"]
        )
        self.rotation_interval.set_selected(
            ROTATION_INTERVALS.index(self._rotation_interval_seconds)
        )
        self.rotation_interval.set_tooltip_text("Auto-rotation interval")
        self.rotation_interval.connect(
            "notify::selected", self._on_rotation_interval_changed
        )
        rotation_row.append(self.rotation_interval)
        self.rotation_previous_button = Gtk.Button(label="Previous")
        self.rotation_previous_button.set_tooltip_text(
            "Reapply the previous wallpaper from saved applied history"
        )
        self.rotation_previous_button.connect(
            "clicked", self._on_rotation_previous
        )
        rotation_row.append(self.rotation_previous_button)
        self.clear_history_button = Gtk.Button(label="Clear history")
        self.clear_history_button.set_tooltip_text(
            "Clear the saved history of applied wallpapers"
        )
        self.clear_history_button.connect(
            "clicked", self._on_clear_applied_history
        )
        rotation_row.append(self.clear_history_button)
        self.rotation_next_button = Gtk.Button(label="Next")
        self.rotation_next_button.set_tooltip_text(
            "Apply another random wallpaper from the current filtered results"
        )
        self.rotation_next_button.connect("clicked", self._on_rotation_next)
        rotation_row.append(self.rotation_next_button)
        rotation_row.set_visible(not self._plain)
        content.append(rotation_row)

        cleanup_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cleanup_row.set_halign(Gtk.Align.CENTER)
        cleanup_row.set_margin_bottom(8)
        self.remove_missing_favorites_button = Gtk.Button(
            label="Remove missing favorites"
        )
        self.remove_missing_favorites_button.connect(
            "clicked", self._on_remove_missing_favorites
        )
        cleanup_row.append(self.remove_missing_favorites_button)
        cleanup_row.set_visible(not self._plain)
        content.append(cleanup_row)
        self._update_missing_favorites_action()
        toolbar_view.set_content(content)

        self.set_content(toolbar_view)
        if self._favorites_load_warning and not self._plain:
            GLib.idle_add(self._show_favorites_load_warning)

        # GTK 4.6+ exposes local file drags through Gdk.FileList. Guard the
        # optional type so older GTK 4 builds can still launch Wallmat.
        if hasattr(Gdk, "FileList"):
            folder_drop = Gtk.DropTarget.new(
                Gdk.FileList.__gtype__, Gdk.DragAction.COPY
            )
            folder_drop.connect("drop", self._on_folder_drop)
            self.add_controller(folder_drop)

        self._wallpaper_dir = os.path.abspath(wallpaper_dir)
        self._scan_and_load(self._wallpaper_dir)
        if self._plain and not self._all_paths:
            self.get_application().plain_exit_code = SCAN_FAILED
            GLib.idle_add(self.get_application().quit)
        self._restore_applied_history()
        if self._sort_mode == "random":
            # The sort preference survives restarts, but the previous
            # process's shuffled list does not. Create a fresh order before
            # filtering so a restored Random order is never empty.
            self._random_order = self._make_random_order(self._all_paths)
        if not self._plain:
            # Apply the restored sort and favorites-only state even when the
            # saved text filter is empty.
            self._refresh_filtered_paths()
            saved_filter = self._preference.get_string(FILTER_KEY, "")
            if saved_filter:
                self.search_entry.set_text(saved_filter)
                self.search_entry.set_visible(True)

        # An explicit --layout argument always wins over the stored
        # preference — that's the whole point of being able to specify it.
        if initial_layout_id in LAYOUT_REGISTRY:
            initial_id = initial_layout_id
        else:
            initial_id = self._preference.get()
            if initial_id not in LAYOUT_REGISTRY:
                initial_id = DEFAULT_LAYOUT_ID
        self._switch_to(initial_id)
        self.layout_selector.set_selected(self._layout_ids.index(initial_id))

        # Restore selection only when the saved file still exists and is
        # visible under the restored folder and filters. Never let stale
        # settings select a missing or currently filtered-out wallpaper.
        if not self._plain:
            self._refresh_recent_selector()
            saved_path = self._preference.get_string(SELECTED_PATH_KEY, "")
            if saved_path and saved_path in self._paths and os.path.isfile(saved_path):
                active_layout = self._layouts.get(self._current_layout_id)
                if active_layout is not None:
                    active_layout.select_path(saved_path)
                self._on_wallpaper_selected(None, saved_path)

    def _on_folder_drop(self, _target, value, _x, _y):
        """Ask before replacing the active wallpaper directory via a file drop."""
        try:
            files = value.get_files()
        except (AttributeError, TypeError):
            say("Drop one wallpaper folder to switch directories.")
            return False

        if len(files) != 1:
            say("Drop exactly one folder to switch wallpaper directories.")
            return False

        path = files[0].get_path()
        if not path or not os.path.isdir(path):
            say("That drop is not a local folder. The wallpaper directory is unchanged.")
            return False

        dialog = Adw.MessageDialog.new(
            self,
            "Switch wallpaper folder?",
            f"Rescan this folder and replace the current wallpaper list?\n\n{path}",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("switch", "Switch folder")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance(
            "switch", Adw.ResponseAppearance.SUGGESTED
        )
        dialog.connect("response", self._on_folder_drop_response, path)
        dialog.present()
        return True

    def _on_folder_drop_response(self, dialog, response, path):
        if response != "switch":
            return

        # Replace the root only after explicit confirmation. Clear root-specific
        # filters so a new folder does not appear empty because of old criteria.
        self._wallpaper_dir = os.path.abspath(path)
        try:
            with open(self._favorites_file, "r", encoding="utf-8") as handle:
                self._favorites = decode_favorites(
                    json.load(handle), self._wallpaper_dir
                )
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError, ValueError) as error:
            say(f"Could not reload favorites for this folder: {error}")
        self._scan_and_load(self._wallpaper_dir)
        self._restore_applied_history()
        self.search_entry.set_text("")
        self.favorites_filter.set_active(False)
        self._refresh_filtered_paths()
        self._refresh_recent_selector()
        say(f"Wallpaper folder changed: {path}")

    def _on_layout_selected(self, dropdown, _pspec):
        selected = dropdown.get_selected()
        if selected < len(self._layout_ids):
            self._switch_to(self._layout_ids[selected])

    def _scan_and_load(self, directory: str):
        # Only offer formats that are both known to work as desktop wallpapers
        # and enabled in this session's GdkPixbuf loaders. In particular, WebP
        # is optional on some distributions and must not be advertised when its
        # loader is missing or disabled.
        safe_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        supported_exts = {
            f".{extension.lower()}"
            for image_format in GdkPixbuf.Pixbuf.get_formats()
            if not image_format.is_disabled()
            for extension in image_format.get_extensions()
            if f".{extension.lower()}" in safe_extensions
        }
        scan_depth = self._preference.get_int(
            SCAN_DEPTH_KEY, DEFAULT_SCAN_DEPTH
        )
        if not 0 <= scan_depth <= MAX_SCAN_DEPTH:
            scan_depth = DEFAULT_SCAN_DEPTH
        paths, scan_errors, truncated = scan_wallpapers(
            directory,
            supported_exts,
            max_wallpapers=MAX_WALLPAPERS,
            max_depth=scan_depth,
        )
        self._scan_errors = list(scan_errors)
        self._all_paths = paths
        self._random_order = self._make_random_order(paths)
        self._paths = list(paths)

        # The window itself has no title bar to display this in, but it's
        # still what shows up in a taskbar, Alt-Tab switcher, or window
        # list — previously the title never changed from a generic
        # "Wallpaper Chooser (Prototype)", so there was no way to tell
        # which folder (or how many wallpapers) a given window was even
        # showing without checking the terminal it was launched from.
        folder_label = os.path.basename(directory.rstrip(os.sep)) or directory
        count_label = str(len(self._paths))
        cap_label = f" — showing first {MAX_WALLPAPERS}" if truncated else ""
        self.set_title(
            f"Wallpaper Chooser — {folder_label} ({count_label}){cap_label}"
        )
        self._scan_limit_notice.set_visible(truncated)
        if truncated:
            print(
                f"Wallpaper scan limit reached ({MAX_WALLPAPERS}); "
                f"additional supported images may have been omitted.",
                file=sys.stderr,
            )

        self._scan_error_notice.set_visible(bool(scan_errors) and not self._plain)
        if scan_errors:
            visible_errors = scan_errors[:3]
            details = "\n".join(visible_errors)
            if len(scan_errors) > len(visible_errors):
                details += f"\n…and {len(scan_errors) - len(visible_errors)} more folder error(s)"
            self._scan_error_notice.set_text(
                f"Some wallpaper folders could not be scanned:\n{details}"
            )
            for error in scan_errors:
                print(f"Wallpaper scan warning: {error}", file=sys.stderr)

        if not self._paths and not self._plain:
            # A scan failure must not masquerade as a genuinely empty folder.
            self._empty_state.set_visible(True)
            if scan_errors:
                self._empty_state.set_title("Could not read wallpaper folder")
                self._empty_state.set_description(
                    "Check the folder path and read permissions. See the "
                    "warning above for the affected location."
                )
            else:
                self._empty_state.set_title(
                    "No matching wallpapers" if self.search_entry.get_text().strip()
                    else "No wallpapers found"
                )
                self._empty_state.set_description(
                    "Try a different filename or folder name."
                    if self.search_entry.get_text().strip()
                    else "This folder has no supported wallpaper images."
                )
        else:
            self._empty_state.set_visible(not self._paths)
            self._empty_state.set_title(
                "No matching wallpapers" if self.search_entry.get_text().strip()
                else "No wallpapers found"
            )
            self._empty_state.set_description(
                "Try a different filename or folder name."
                if self.search_entry.get_text().strip()
                else "This folder has no supported wallpaper images."
            )

        if not self._paths and self._plain:
            # --plain stdout is reserved for a selected path; diagnostics go
            # to stderr so shell pipelines can distinguish an empty scan.
            print(f"No wallpapers found under {directory}; pass a readable "
                  "directory containing supported images.", file=sys.stderr)

    @staticmethod
    def _modified_timestamp(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            # A file can disappear between scanning and sorting.
            return 0.0

    def _image_dimensions(self, path: str) -> tuple[int, int] | None:
        """Read image dimensions from its header and cache by file fingerprint."""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        cached = self._resolution_cache.get(path)
        if cached and cached[0] == fingerprint:
            return cached[1]
        dimensions = None
        try:
            info = GdkPixbuf.Pixbuf.get_file_info(path)
            if info and info[1] > 0 and info[2] > 0:
                dimensions = (info[1], info[2])
        except (GLib.Error, OSError, TypeError):
            pass
        self._resolution_cache[path] = (fingerprint, dimensions)
        return dimensions

    def _on_sort_selected(self, dropdown, _pspec):
        modes = ("name", "newest", "oldest", "resolution", "random", "folder")
        selected = dropdown.get_selected()
        if selected >= len(modes):
            return
        new_mode = modes[selected]
        if new_mode == "random" and self._sort_mode != "random":
            self._random_order = self._make_random_order(self._all_paths)
        self._sort_mode = new_mode
        if not self._plain:
            self._preference.set_string(SORT_KEY, new_mode)
        self._refresh_filtered_paths()

    def _on_search_changed(self, entry):
        if not self._plain:
            self._preference.set_string(FILTER_KEY, entry.get_text())
        self._refresh_filtered_paths()

    def _on_favorites_filter_toggled(self, button):
        self._favorites_only = button.get_active()
        if not self._plain:
            self._preference.set_boolean(
                FAVORITES_ONLY_KEY, self._favorites_only
            )
        self._refresh_filtered_paths()

    def _refresh_filtered_paths(self):
        query = self.search_entry.get_text().strip().casefold()
        if self._sort_mode == "newest":
            paths = sorted(
                self._all_paths,
                key=lambda path: (self._modified_timestamp(path), path.casefold()),
                reverse=True,
            )
        elif self._sort_mode == "oldest":
            paths = sorted(
                self._all_paths,
                key=lambda path: (self._modified_timestamp(path), path.casefold()),
            )
        elif self._sort_mode == "resolution":
            paths = sort_by_resolution(self._all_paths, self._image_dimensions)
        elif self._sort_mode == "random":
            paths = self._random_order
        elif self._sort_mode == "folder":
            def folder_key(path):
                relative = os.path.relpath(path, self._wallpaper_dir)
                parts = relative.split(os.sep)
                folder = parts[0] if len(parts) > 1 else ""
                return (folder.casefold(), path.casefold())
            paths = sorted(self._all_paths, key=folder_key)
        else:
            paths = sorted(self._all_paths, key=lambda path: path.casefold())
        if self._favorites_only:
            paths = [path for path in paths if path in self._favorites]
        if query:
            # Match both the basename and its path within the selected root.
            # The basename keeps the common filename-search behavior while
            # relative paths make nested wallpaper folders discoverable.
            root = self._wallpaper_dir
            paths = [
                path for path in paths
                if query in os.path.basename(path).casefold()
                or query in os.path.relpath(path, root).casefold()
            ]
        self._paths = list(paths)

        for layout_id, layout in self._layouts.items():
            if layout_id == self._current_layout_id:
                layout.load_wallpapers(self._paths)
            else:
                # Refresh inactive layouts only when the user switches to
                # them, keeping rapid search edits from doing hidden work.
                self._stale_layouts.add(layout_id)

        self._empty_state.set_visible(not self._paths)
        has_query = bool(query)
        if not self._all_paths and self._scan_errors:
            self._empty_state.set_title("Could not read wallpaper folder")
            self._empty_state.set_description(
                "Check that the selected folder exists and that you have "
                "permission to read it. See the warning above for details."
            )
        else:
            no_results_title = (
                "No matching wallpapers" if has_query
                else "No favorite wallpapers" if self._favorites_only
                else "No wallpapers found"
            )
            self._empty_state.set_title(no_results_title)
            if self._favorites_only and not self._paths:
                self._empty_state.set_description(
                    "Try adding favorites or turn off the Favorites only filter."
                )
            else:
                self._empty_state.set_description(
                    "Try a different filename or folder filter."
                    if has_query else "This folder has no supported wallpaper images."
                )

    def _switch_to(self, layout_id: str):
        if layout_id == self._current_layout_id:
            return
        if layout_id not in LAYOUT_REGISTRY:
            return

        if self._current_layout_id is not None:
            old_layout = self._layouts.get(self._current_layout_id)
            if old_layout is not None:
                old_layout.on_deactivate()

        if layout_id not in self._layouts:
            layout = LAYOUT_REGISTRY[layout_id]()
            layout.connect("wallpaper-selected", self._on_wallpaper_selected)
            widget = layout.get_widget()  # build() happens here, lazily
            layout.load_wallpapers(self._paths)
            self.stack.add_named(widget, layout_id)
            self._layouts[layout_id] = layout
        else:
            layout = self._layouts[layout_id]
            if layout_id in self._stale_layouts:
                layout.load_wallpapers(self._paths)
                self._stale_layouts.discard(layout_id)

        self.stack.set_visible_child_name(layout_id)
        layout.on_activate()
        self._current_layout_id = layout_id
        if not self._plain:
            self._preference.set(layout_id)

    def _register_focus_colors(self, window):
        register_focus_colors(self.get_display())

    def _on_wallpaper_selected(self, layout, path):
        if self._plain:
            set_quiet(True)  # re-assert; guards against any late prints
            print(path, flush=True)
            self.get_application().plain_exit_code = SUCCESS
            self.close()
            return
        self._selected_path = path
        self._preference.set_string(SELECTED_PATH_KEY, path)
        self._load_selected_metadata(path)
        self.preview_button.set_sensitive(os.path.isfile(path))
        self.set_wallpaper_button.set_sensitive(True)
        self.apply_matugen_button.set_sensitive(True)
        self.favorite_button.set_sensitive(True)
        self.export_favorites_button.set_sensitive(True)
        self._update_favorite_button()
        say(f"Selected: {path}")

    def _restore_applied_history(self):
        saved = self._preference.get_strv(APPLIED_HISTORY_KEY)
        self._rotation_history = for_collection(
            saved, self._all_paths, MAX_APPLIED_HISTORY
        )
        self._rotation_history_index = len(self._rotation_history) - 1
        self._update_clear_history_button()

    def _record_applied_history(self, path: str):
        if self._history_navigation:
            try:
                self._rotation_history_index = self._rotation_history.index(path)
            except ValueError:
                pass
            return
        saved = self._preference.get_strv(APPLIED_HISTORY_KEY)
        updated = append_applied(saved, path, MAX_APPLIED_HISTORY)
        self._preference.set_strv(APPLIED_HISTORY_KEY, updated)
        self._rotation_history = for_collection(
            updated, self._all_paths, MAX_APPLIED_HISTORY
        )
        self._rotation_history_index = len(self._rotation_history) - 1
        self._update_clear_history_button()

    def _update_clear_history_button(self):
        if hasattr(self, "clear_history_button"):
            has_history = bool(
                self._preference.get_strv(APPLIED_HISTORY_KEY)
                or self._preference.get_strv(RECENT_PATHS_KEY)
            )
            self.clear_history_button.set_sensitive(has_history)
            self.rotation_previous_button.set_sensitive(
                self._rotation_history_index > 0
            )

    def _on_clear_applied_history(self, _button):
        self._preference.set_strv(APPLIED_HISTORY_KEY, [])
        self._preference.set_strv(RECENT_PATHS_KEY, [])
        self._rotation_history = []
        self._rotation_history_index = -1
        self._refresh_recent_selector()
        self._update_clear_history_button()
        say("Applied wallpaper history cleared.")

    def _refresh_recent_selector(self):
        """Show existing recent wallpapers available in the scanned folder."""
        saved = self._preference.get_strv(RECENT_PATHS_KEY)
        self._recent_paths = [
            path for path in saved
            if isinstance(path, str) and os.path.isfile(path)
            and path in self._all_paths
        ][:MAX_RECENT_WALLPAPERS]
        labels = []
        for path in self._recent_paths:
            parent = os.path.basename(os.path.dirname(path))
            name = os.path.basename(path)
            labels.append(f"{name} — {parent}" if parent else name)
        self._recent_selector.set_model(
            Gtk.StringList.new(labels or ["No recent wallpapers"])
        )
        self._recent_selector.set_selected(Gtk.INVALID_LIST_POSITION)
        self._recent_selector.set_sensitive(bool(labels))

    def _remember_recent_path(self, path: str):
        if not os.path.isfile(path):
            return
        saved = self._preference.get_strv(RECENT_PATHS_KEY)
        recent = [path] + [item for item in saved if item != path and isinstance(item, str)]
        recent = [item for item in recent if os.path.isfile(item)][:MAX_RECENT_WALLPAPERS]
        self._preference.set_strv(RECENT_PATHS_KEY, recent)
        self._refresh_recent_selector()

    def _on_recent_selected(self, dropdown, _pspec):
        if self._plain:
            return
        position = dropdown.get_selected()
        if position == Gtk.INVALID_LIST_POSITION or position >= len(self._recent_paths):
            return
        path = self._recent_paths[position]
        if not os.path.isfile(path):
            self._refresh_recent_selector()
            say("That recent wallpaper is no longer available.")
            return
        if path not in self._all_paths:
            say("That wallpaper is outside the currently opened folder.")
            return
        if path not in self._paths:
            # A recent item may be hidden by the current text or favorites
            # filter. Clear both filters so the selected item becomes visible.
            self.search_entry.set_text("")
            self.favorites_filter.set_active(False)
            self._refresh_filtered_paths()
        layout = self._layouts.get(self._current_layout_id)
        if layout is not None:
            layout.select_path(path)
        self._on_wallpaper_selected(layout, path)

    def _load_selected_metadata(self, path: str):
        """Read image metadata off the GTK thread and ignore stale results."""
        if self._plain:
            return
        self._metadata_label.set_text("Loading wallpaper details…")
        self._metadata_row.set_visible(True)

        def inspect_file():
            try:
                stat = os.stat(path)
                image_format, width, height = GdkPixbuf.Pixbuf.get_file_info(path)
                if width <= 0 or height <= 0:
                    raise OSError("Image dimensions are unavailable")
                size = stat.st_size
                if size < 1024 * 1024:
                    size_text = f"{size / 1024:.1f} KiB"
                else:
                    size_text = f"{size / (1024 * 1024):.2f} MiB"
                modified = __import__("datetime").datetime.fromtimestamp(
                    stat.st_mtime
                ).astimezone().strftime("%Y-%m-%d %H:%M")
                ratio = width / height
                format_name = (
                    image_format.get_name() if image_format else "Unknown format"
                )
                details = (
                    f"{width} × {height} px · {format_name} · "
                    f"{ratio:.3f}:1 · {size_text} · Modified {modified}\n{path}"
                )
            except (GLib.Error, OSError, TypeError, ValueError) as error:
                details = f"Could not read wallpaper metadata: {error}\n{path}"

            def update_label():
                if self._selected_path == path:
                    self._metadata_label.set_text(details)
                    self._metadata_row.set_visible(True)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(update_label)

        threading.Thread(target=inspect_file, daemon=True).start()

    def _on_copy_metadata(self, _button):
        display = Gdk.Display.get_default()
        if display is None:
            say("Clipboard is unavailable.")
            return
        display.get_clipboard().set(self._metadata_label.get_text())
        say("Wallpaper details copied.")

    def _on_hide_metadata(self, _button):
        self._metadata_row.set_visible(False)

    def _update_favorite_button(self):
        if self._selected_path in self._favorites:
            self.favorite_button.set_label("Remove favorite")
        else:
            self.favorite_button.set_label("Add to favorites")

    def _update_missing_favorites_action(self):
        missing_count = sum(
            not os.path.isfile(path) for path in self._favorites
        )
        self.remove_missing_favorites_button.set_label(
            f"Remove {missing_count} missing favorite(s)"
        )
        self.remove_missing_favorites_button.set_visible(
            bool(missing_count) and not self._plain
        )

    def _on_remove_missing_favorites(self, button):
        original_favorites = self._favorites.copy()
        existing_favorites = {
            path for path in self._favorites if os.path.isfile(path)
        }
        removed_count = len(self._favorites) - len(existing_favorites)
        if not removed_count:
            self._update_missing_favorites_action()
            say("No missing favorites to remove.")
            return

        self._favorites = existing_favorites
        try:
            self._save_favorites()
        except OSError as error:
            self._favorites = original_favorites
            self._update_missing_favorites_action()
            say(f"Could not save cleaned favorites: {error}")
            return

        self._update_missing_favorites_action()
        self._update_favorite_button()
        say(f"Removed {removed_count} missing favorite(s).")

    def _backup_corrupt_favorites(self) -> str:
        """Preserve an unreadable favorites file without overwriting older backups."""
        backup_path = self._favorites_file + ".corrupt"
        suffix = 1
        while os.path.exists(backup_path):
            backup_path = f"{self._favorites_file}.corrupt.{suffix}"
            suffix += 1
        shutil.copy2(self._favorites_file, backup_path)
        return backup_path

    def _show_favorites_load_warning(self):
        dialog = Adw.MessageDialog.new(
            self, "Favorites could not be loaded", self._favorites_load_warning
        )
        dialog.add_response("ok", "OK")
        dialog.set_close_response("ok")
        dialog.set_default_response("ok")
        dialog.present()
        return GLib.SOURCE_REMOVE

    def _save_favorites(self):
        if self._favorites_write_blocked:
            raise PermissionError(
                "favorites are protected because their recovery backup failed"
            )
        directory = os.path.dirname(self._favorites_file)
        os.makedirs(directory, exist_ok=True)
        temporary_path = self._favorites_file + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(
                    encode_favorites(self._favorites, self._wallpaper_dir),
                    handle,
                    indent=2,
                )
                handle.write("\n")
            os.replace(temporary_path, self._favorites_file)
        except OSError:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise

    def _on_toggle_favorite(self, button):
        path = self._selected_path
        if not path:
            return
        original_favorites = self._favorites.copy()
        if path in self._favorites:
            self._favorites.remove(path)
        else:
            self._favorites.add(path)
        try:
            self._save_favorites()
        except OSError as error:
            # Keep the in-memory state and visible filter consistent with
            # disk when saving fails; the next action must not assume success.
            self._favorites = original_favorites
            self._update_favorite_button()
            self._update_missing_favorites_action()
            if self._favorites_only:
                self._refresh_filtered_paths()
            say(f"Could not save favorites: {error}")
            return

        self._update_favorite_button()
        self._update_missing_favorites_action()
        if self._favorites_only:
            self._refresh_filtered_paths()
        say(f"Favorites saved: {len(self._favorites)}")

    def _on_export_favorites(self, button):
        try:
            directory = os.path.dirname(self._favorites_export_file)
            os.makedirs(directory, exist_ok=True)
            existing = sorted(path for path in self._favorites if os.path.isfile(path))
            missing_count = len(self._favorites) - len(existing)
            with open(self._favorites_export_file, "w", encoding="utf-8") as handle:
                for path in existing:
                    handle.write(path + "\n")
            message = (
                f"Exported {len(existing)} existing favorites to "
                f"{self._favorites_export_file}"
            )
            if missing_count:
                message += f"; omitted {missing_count} missing file(s)"
            say(message)
        except OSError as error:
            say(f"Could not export favorites: {error}")

    def _on_window_close_request(self, *_args):
        """Stop session-only rotation and preserve plain-mode cancellation."""
        if (
            self._plain
            and getattr(self.get_application(), "plain_exit_code", CANCELLED) != SUCCESS
        ):
            self.get_application().plain_exit_code = CANCELLED
        if self._rotation_source_id is not None:
            GLib.source_remove(self._rotation_source_id)
            self._rotation_source_id = None
        return False

    def _on_auto_rotate_toggled(self, button):
        if button.get_active():
            if self._rotation_source_id is None:
                self._rotation_source_id = GLib.timeout_add_seconds(
                    self._rotation_interval_seconds,
                    self._on_auto_rotate_tick,
                )
            say("Auto-rotation enabled for this session.")
        else:
            if self._rotation_source_id is not None:
                GLib.source_remove(self._rotation_source_id)
                self._rotation_source_id = None
            say("Auto-rotation disabled.")

    def _on_rotation_interval_changed(self, dropdown, _pspec):
        selected = dropdown.get_selected()
        if selected >= len(ROTATION_INTERVALS):
            return
        self._rotation_interval_seconds = ROTATION_INTERVALS[selected]
        self._preference.set_int(
            AUTO_ROTATE_INTERVAL_KEY, self._rotation_interval_seconds
        )
        if self.auto_rotate_toggle.get_active():
            if self._rotation_source_id is not None:
                GLib.source_remove(self._rotation_source_id)
            self._rotation_source_id = GLib.timeout_add_seconds(
                self._rotation_interval_seconds,
                self._on_auto_rotate_tick,
            )

    def _on_auto_rotate_tick(self):
        if not self.auto_rotate_toggle.get_active():
            self._rotation_source_id = None
            return GLib.SOURCE_REMOVE
        self._on_rotation_next(None)
        return GLib.SOURCE_CONTINUE

    def _make_random_order(self, paths: list[str]) -> list[str]:
        """Shuffle all paths while deferring recently chosen wallpapers."""
        recent = self._preference.get_strv(RECENT_RANDOM_PATHS_KEY)
        return shuffle_with_recent_last(paths, recent)

    def _choose_random_wallpaper(self, candidates: list[str]) -> str | None:
        """Choose outside the recent history, resetting when the pool is exhausted."""
        history_limit = self._preference.get_int(
            RANDOM_HISTORY_LIMIT_KEY, DEFAULT_RANDOM_HISTORY_LIMIT
        )
        if not 0 <= history_limit <= MAX_RANDOM_HISTORY:
            history_limit = DEFAULT_RANDOM_HISTORY_LIMIT
        selected, updated_history = choose_next(
            candidates,
            self._preference.get_strv(RECENT_RANDOM_PATHS_KEY),
            history_limit,
        )
        self._preference.set_strv(
            RECENT_RANDOM_PATHS_KEY, updated_history
        )
        return selected

    def _on_rotation_next(self, _button):
        if self._plain:
            return
        candidates = [
            path for path in self._paths
            if os.path.isfile(path)
        ]
        if not candidates:
            say("No available wallpapers match the current filters.")
            return
        path = self._choose_random_wallpaper(candidates)
        if path is None:
            return
        self._on_wallpaper_selected(None, path)
        self._on_apply_wallpaper(None)

    def _on_rotation_previous(self, _button):
        if self._plain:
            return
        for index in range(self._rotation_history_index - 1, -1, -1):
            path = self._rotation_history[index]
            if os.path.isfile(path):
                self._history_navigation = True
                try:
                    self._on_wallpaper_selected(None, path)
                    self._on_apply_wallpaper(None)
                finally:
                    self._history_navigation = False
                return
        say("There is no previous wallpaper in the saved history.")

    def _on_surprise_me(self, button):
        """Choose and apply a random wallpaper from the currently filtered set."""
        if self._plain:
            return

        candidates = [path for path in self._paths if os.path.isfile(path)]
        if not candidates:
            say("No available wallpapers match the current filters.")
            return

        path = self._choose_random_wallpaper(candidates)
        if path is None:
            return
        self._on_wallpaper_selected(None, path)
        self._on_apply_wallpaper(button)

    def _on_open_preview(self, _button):
        """Show the selected image in a fullscreen, pannable preview."""
        path = self._selected_path
        if self._plain or not path:
            return
        if not os.path.isfile(path):
            say("That wallpaper is no longer available.")
            self.preview_button.set_sensitive(False)
            return

        window = Gtk.Window(
            title=os.path.basename(path),
            transient_for=self,
            modal=True,
        )
        window.set_default_size(1100, 750)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)
        outer.set_margin_start(12)
        outer.set_margin_end(12)
        outer.add_css_class("wallmat-preview-dark")

        # Scope preview colors to this dialog's uniquely tagged container.
        # The CSS provider never changes GNOME's global color-scheme setting.
        preview_css = Gtk.CssProvider()
        preview_css.load_from_data(
            b".wallmat-preview-light { background-color: #f6f5f4; color: #241f31; }"
            b".wallmat-preview-dark { background-color: #242424; color: #f6f5f4; }"
            b".wallmat-preview-light label { color: #241f31; }"
            b".wallmat-preview-dark label { color: #f6f5f4; }"
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            preview_css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        def remove_preview_css(*_args):
            Gtk.StyleContext.remove_provider_for_display(
                self.get_display(), preview_css
            )
            return False

        window.connect("close-request", remove_preview_css)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        picture = Gtk.Picture()
        picture.set_can_shrink(True)
        picture.set_halign(Gtk.Align.START)
        picture.set_valign(Gtk.Align.START)
        scroller.set_child(picture)

        status = Gtk.Label(label="Loading full-resolution image…")
        status.add_css_class("dim-label")
        status.set_wrap(True)
        outer.append(status)
        outer.append(scroller)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls.set_halign(Gtk.Align.CENTER)
        light_button = Gtk.ToggleButton(label="Light")
        dark_button = Gtk.ToggleButton(label="Dark")
        dark_button.set_group(light_button)
        dark_button.set_active(True)

        def set_preview_scheme(button, scheme):
            if not button.get_active():
                return
            outer.remove_css_class("wallmat-preview-light")
            outer.remove_css_class("wallmat-preview-dark")
            outer.add_css_class(f"wallmat-preview-{scheme}")

        light_button.connect("toggled", set_preview_scheme, "light")
        dark_button.connect("toggled", set_preview_scheme, "dark")
        controls.append(light_button)
        controls.append(dark_button)
        zoom_label = Gtk.Label(label="Zoom")
        zoom = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.25, 2.0, 0.25
        )
        zoom.set_value(0.5)
        zoom.set_digits(2)
        zoom.set_draw_value(True)
        zoom.set_size_request(240, -1)
        zoom.set_sensitive(False)
        controls.append(zoom_label)
        controls.append(zoom)
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda *_: window.close())
        controls.append(close_button)

        apply_button = Gtk.Button(label="Set as wallpaper")
        apply_button.add_css_class("suggested-action")
        apply_button.connect(
            "clicked",
            lambda *_: (self._on_apply_wallpaper(None), window.close()),
        )
        controls.append(apply_button)
        outer.append(controls)
        window.set_child(outer)

        image_state = {"pixbuf": None}

        def update_zoom(scale):
            pixbuf = image_state["pixbuf"]
            if pixbuf is None:
                return
            factor = scale.get_value()
            picture.set_size_request(
                max(1, round(pixbuf.get_width() * factor)),
                max(1, round(pixbuf.get_height() * factor)),
            )

        zoom.connect("value-changed", update_zoom)

        def load_image():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
                error_message = None
            except (GLib.Error, OSError) as error:
                pixbuf = None
                error_message = str(error)

            def show_image():
                if pixbuf is None:
                    status.set_text(f"Could not load preview: {error_message}")
                    apply_button.set_sensitive(False)
                    return GLib.SOURCE_REMOVE
                image_state["pixbuf"] = pixbuf
                picture.set_pixbuf(pixbuf)
                update_zoom(zoom)
                zoom.set_sensitive(True)
                status.set_text(
                    f"{pixbuf.get_width()} × {pixbuf.get_height()} px · "
                    "Scroll to pan at higher zoom"
                )
                return GLib.SOURCE_REMOVE

            GLib.idle_add(show_image)

        threading.Thread(target=load_image, daemon=True).start()
        window.present()
        window.fullscreen()

    def _on_apply_wallpaper(self, button):
        path = self._selected_path
        if not path:
            return False
        try:
            settings = Gio.Settings.new("org.gnome.desktop.background")
            uri = GLib.filename_to_uri(path)
            keys = settings.list_keys()
            updated = False
            if "picture-uri" in keys:
                settings.set_string("picture-uri", uri)
                updated = True
            if "picture-uri-dark" in keys:
                settings.set_string("picture-uri-dark", uri)
                updated = True
            if not updated:
                say("GNOME exposes no supported wallpaper URI setting.")
                return False
            self._record_applied_history(path)
            self._remember_recent_path(path)
            say(f"Wallpaper applied: {path}")
            return True
        except (GLib.Error, OSError, TypeError) as error:
            say(f"Could not set GNOME wallpaper: {error}")
            return False

    def _on_apply_matugen(self, button):
        path = self._selected_path
        if not path:
            return

        # Apply the wallpaper independently: a missing or failing Matugen
        # executable must not undo or prevent the GNOME background change.
        self._on_apply_wallpaper(button)
        command = ["matugen", "image", path, *self._matugen_args]

        def run_matugen():
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    message = "Matugen completed successfully."
                else:
                    detail = (result.stderr or result.stdout).strip()
                    if not detail:
                        detail = f"exit status {result.returncode}"
                    # Keep the notification concise; full logs remain outside
                    # the UI rather than flooding the announcement channel.
                    detail = detail.splitlines()[-1][:240]
                    message = f"Matugen failed: {detail}"
            except OSError as error:
                message = f"Could not run Matugen: {error}"
            GLib.idle_add(say, message)

        # Capture output off the GTK thread so neither Matugen execution nor
        # a verbose stderr pipe can freeze the window.
        threading.Thread(target=run_matugen, daemon=True).start()

    def _show_shortcuts(self, *_args):
        body = (
            "Global shortcuts\n"
            "Ctrl + F — show and focus the wallpaper filter\n"
            "Escape — clear and hide the filter; press again to close\n"
            "Enter — select the focused wallpaper where the active layout supports it\n"
            "← / → — move focus in layouts that support keyboard navigation\n\n"
            "Layout differences\n"
            "Stacked Deck and interactive layouts can handle clicks and selection "
            "differently. Arrow and Enter behavior depends on the active layout; "
            "not every layout exposes the same keyboard navigation."
        )
        dialog = Adw.MessageDialog.new(self, "Keyboard shortcuts", body)
        dialog.add_response("close", "Close")
        dialog.set_close_response("close")
        dialog.set_default_response("close")
        dialog.present()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_question:
            self._show_shortcuts()
            return True
        if keyval == Gdk.KEY_f and state & Gdk.ModifierType.CONTROL_MASK:
            self.search_entry.set_visible(True)
            self.search_entry.grab_focus()
            return True
        if keyval == Gdk.KEY_Escape:
            if self.search_entry.get_visible():
                self.search_entry.set_text("")
                self.search_entry.set_visible(False)
                self.stack.grab_focus()
            else:
                self.close()
            return True
        return False
