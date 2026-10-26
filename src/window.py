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
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk

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

SCHEMA_ID = "dev.sakib.Wallmat"
SETTINGS_KEY = "selected-layout"
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
        self._memory_value = DEFAULT_LAYOUT_ID
        try:
            schema_source = Gio.SettingsSchemaSource.get_default()
            if schema_source and schema_source.lookup(SCHEMA_ID, True):
                self._settings = Gio.Settings.new(SCHEMA_ID)
        except GLib.Error:
            self._settings = None

    def get(self) -> str:
        if self._settings is not None:
            return self._settings.get_string(SETTINGS_KEY)
        return self._memory_value

    @property
    def persistent(self) -> bool:
        return self._settings is not None

    def set(self, layout_id: str):
        if self._settings is not None:
            self._settings.set_string(SETTINGS_KEY, layout_id)
        else:
            self._memory_value = layout_id


class WallpaperChooserWindow(Adw.ApplicationWindow):
    def __init__(self, app, wallpaper_dir: str, initial_layout_id: str | None = None,
                 plain: bool = False, matugen_args: list[str] | None = None):
        super().__init__(application=app, title="Wallpaper Chooser")
        self._plain = plain
        self._matugen_args = list(
            matugen_args or ["--type", "scheme-smart", "--mode", "dark"]
        )
        self._selected_path: str | None = None
        config_dir = os.path.expanduser("~/.config/wallmat")
        self._favorites_file = os.path.join(config_dir, "favorites.json")
        self._favorites_export_file = os.path.join(config_dir, "favorites.txt")
        self._favorites: set[str] = set()
        try:
            with open(self._favorites_file, "r", encoding="utf-8") as handle:
                saved_favorites = json.load(handle)
            if isinstance(saved_favorites, list):
                self._favorites = {
                    path for path in saved_favorites if isinstance(path, str)
                }
        except (OSError, json.JSONDecodeError):
            pass
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

        self._settings_notice = Gtk.Label(
            label=(
                "Layout preference will not persist because the Wallmat "
                "GSettings schema is unavailable. See schema installation "
                "instructions in README.md."
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
        content.append(content_overlay)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.set_halign(Gtk.Align.CENTER)
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
        content.append(layout_row)

        self.set_wallpaper_button = Gtk.Button(label="Set as wallpaper")
        self.set_wallpaper_button.set_sensitive(False)
        self.set_wallpaper_button.connect("clicked", self._on_apply_wallpaper)
        self.apply_matugen_button = Gtk.Button(label="Apply wallpaper + Matugen")
        self.apply_matugen_button.add_css_class("suggested-action")
        self.apply_matugen_button.set_sensitive(False)
        self.apply_matugen_button.connect("clicked", self._on_apply_matugen)
        self.favorite_button = Gtk.Button(label="Add to favorites")
        self.favorite_button.set_sensitive(False)
        self.favorite_button.connect("clicked", self._on_toggle_favorite)
        self.export_favorites_button = Gtk.Button(label="Export favorites")
        self.export_favorites_button.connect("clicked", self._on_export_favorites)
        action_row.append(self.set_wallpaper_button)
        action_row.append(self.apply_matugen_button)
        action_row.append(self.favorite_button)
        action_row.append(self.export_favorites_button)
        # Plain mode is a path picker for shell pipelines, not a desktop
        # wallpaper manager; keep unrelated apply/favorites actions hidden.
        action_row.set_visible(not self._plain)
        content.append(action_row)

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

        self._wallpaper_dir = wallpaper_dir
        self._scan_and_load(wallpaper_dir)

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

    def _on_layout_selected(self, dropdown, _pspec):
        selected = dropdown.get_selected()
        if selected < len(self._layout_ids):
            self._switch_to(self._layout_ids[selected])

    def _scan_and_load(self, directory: str):
        supported_exts = (".png", ".jpg", ".jpeg", ".webp")
        paths = []
        truncated = False
        if os.path.isdir(directory):
            for root, dirs, files in os.walk(directory):
                # Make which files are included reproducible when the cap is
                # reached, and avoid descending further once enough images
                # have been collected.
                dirs.sort()
                files.sort()
                for f in files:
                    if f.lower().endswith(supported_exts):
                        paths.append(os.path.join(root, f))
                        if len(paths) >= MAX_WALLPAPERS:
                            truncated = True
                            break
                if truncated:
                    break
        self._all_paths = paths
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

        if not self._paths:
            # --plain is a stdout pipeline contract: diagnostics must never
            # be mistaken for the selected wallpaper path.
            print(f"No wallpapers found under {directory}; pass a directory "
                  f"with .png/.jpg/.webp files as argv[1].", file=sys.stderr)
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

    def _on_search_changed(self, entry):
        query = entry.get_text().strip().casefold()
        if query:
            # Match both the basename and its path within the selected root.
            # The basename keeps the common filename-search behavior while
            # relative paths make nested wallpaper folders discoverable.
            root = self._wallpaper_dir
            self._paths = [
                path for path in self._all_paths
                if query in os.path.basename(path).casefold()
                or query in os.path.relpath(path, root).casefold()
            ]
        else:
            self._paths = list(self._all_paths)

        for layout_id, layout in self._layouts.items():
            if layout_id == self._current_layout_id:
                layout.load_wallpapers(self._paths)
            else:
                # Refresh inactive layouts only when the user switches to
                # them, keeping rapid search edits from doing hidden work.
                self._stale_layouts.add(layout_id)

        self._empty_state.set_visible(not self._paths)
        has_query = bool(query)
        self._empty_state.set_title(
            "No matching wallpapers" if has_query else "No wallpapers found"
        )
        self._empty_state.set_description(
            "Try a different filename filter."
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
        self._preference.set(layout_id)

    def _register_focus_colors(self, window):
        register_focus_colors(self.get_display())

    def _on_wallpaper_selected(self, layout, path):
        if self._plain:
            set_quiet(True)  # re-assert; guards against any late prints
            print(path)
            self.close()
            return
        self._selected_path = path
        self.set_wallpaper_button.set_sensitive(True)
        self.apply_matugen_button.set_sensitive(True)
        self.favorite_button.set_sensitive(True)
        self.export_favorites_button.set_sensitive(True)
        self._update_favorite_button()
        say(f"Selected: {path}")

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

    def _save_favorites(self):
        directory = os.path.dirname(self._favorites_file)
        os.makedirs(directory, exist_ok=True)
        temporary_path = self._favorites_file + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(sorted(self._favorites), handle, indent=2)
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
        if path in self._favorites:
            self._favorites.remove(path)
        else:
            self._favorites.add(path)
        try:
            self._save_favorites()
            self._update_favorite_button()
            self._update_missing_favorites_action()
            say(f"Favorites saved: {len(self._favorites)}")
        except OSError as error:
            say(f"Could not save favorites: {error}")

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

    def _on_apply_wallpaper(self, button):
        path = self._selected_path
        if not path:
            return
        try:
            settings = Gio.Settings.new("org.gnome.desktop.background")
            uri = GLib.filename_to_uri(path)
            keys = settings.list_keys()
            if "picture-uri" in keys:
                settings.set_string("picture-uri", uri)
            if "picture-uri-dark" in keys:
                settings.set_string("picture-uri-dark", uri)
            say(f"Wallpaper applied: {path}")
        except (GLib.Error, OSError, TypeError) as error:
            say(f"Could not set GNOME wallpaper: {error}")

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

    def _on_key_pressed(self, controller, keyval, keycode, state):
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
