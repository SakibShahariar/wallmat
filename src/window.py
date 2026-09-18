"""
WallpaperChooserWindow: hosts a Gtk.Stack of lazily-built layouts. There's
no in-app UI for switching between them (no header bar, so no popover to
put a switcher in) — the layout is picked via `--layout` at the command
line. Whichever one is active is persisted to GSettings on every switch
(currently: only the `--layout`-selected one, or the previous session's,
since there's no in-app trigger) so it's remembered across launches (per
spec section 7: "Mood/preference persisted in GSettings").

NOTE on the GSettings schema: this uses a schema id
(org.example.WallpaperChooserPrototype) that is NOT installed on the
system by default. GSettings requires a compiled schema file to exist
under a glib schema directory before Gio.Settings.new() will succeed —
if you see a GLib.Error about an unknown schema when running this, that's
why. A minimal schema XML + install command is included at the bottom of
this file's module docstring for reference; for a quick local test
without installing anything, `_LayoutPreference` below falls back to an
in-memory Python variable if the schema isn't found, so the app still
runs — you just won't get persistence across restarts until the schema
is installed.

--- schema install reference (not run automatically) ---
Save as org.example.WallpaperChooserPrototype.gschema.xml:

    <?xml version="1.0" encoding="UTF-8"?>
    <schemalist>
      <schema id="org.example.WallpaperChooserPrototype" path="/org/example/wallpaperchooserprototype/">
        <key name="selected-layout" type="s">
          <default>'split_screen'</default>
          <summary>Last-used layout id</summary>
        </key>
      </schema>
    </schemalist>

Then:
    mkdir -p ~/.local/share/glib-2.0/schemas
    cp org.example.WallpaperChooserPrototype.gschema.xml ~/.local/share/glib-2.0/schemas/
    glib-compile-schemas ~/.local/share/glib-2.0/schemas/
"""

import os

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

SCHEMA_ID = "org.example.WallpaperChooserPrototype"
SETTINGS_KEY = "selected-layout"
DEFAULT_LAYOUT_ID = "split_screen"

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

    def set(self, layout_id: str):
        if self._settings is not None:
            self._settings.set_string(SETTINGS_KEY, layout_id)
        else:
            self._memory_value = layout_id


class WallpaperChooserWindow(Adw.ApplicationWindow):
    def __init__(self, app, wallpaper_dir: str, initial_layout_id: str | None = None,
                 plain: bool = False):
        super().__init__(application=app, title="Wallpaper Chooser (Prototype)")
        self._plain = plain
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
        self._layouts: dict[str, object] = {}
        self._current_layout_id: str | None = None

        toolbar_view = Adw.ToolbarView()

        # No header bar at all, for any launch mode — per explicit
        # request. This removes the layout-switcher popover UI entirely
        # (it lived in the header bar's grid-icon button) and, since
        # standard GTK4 CSD apps have no window chrome without a header
        # bar, also removes the close/minimize/maximize buttons and drag
        # area universally, not just for --layout launches. Going
        # forward, --layout at the command line is the only way to pick
        # a layout — there's no in-app UI for it anymore. Escape still
        # closes the window (wired up above); there's no titlebar
        # fallback for moving the window without a window manager
        # shortcut for that.
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)

        # Empty-state message: previously, a folder with no supported
        # images only printed to the TERMINAL the app was launched from —
        # the window itself just opened blank with no explanation, which
        # only makes sense if you're the person who launched it and can
        # see that terminal. Shown/hidden once, right after the initial
        # scan (this prototype doesn't rescan directories at runtime).
        content_overlay = Gtk.Overlay()
        content_overlay.set_child(self.stack)
        self._empty_state = Adw.StatusPage()
        self._empty_state.set_icon_name("folder-open-symbolic")
        self._empty_state.set_title("No wallpapers found")
        self._empty_state.set_description(
            "This folder has no .png, .jpg, or .webp files. "
            "Launch again with a different directory."
        )
        self._empty_state.set_visible(False)
        content_overlay.add_overlay(self._empty_state)
        toolbar_view.set_content(content_overlay)

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

    def _scan_and_load(self, directory: str):
        supported_exts = (".png", ".jpg", ".jpeg", ".webp")
        paths = []
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory):
                for f in files:
                    if f.lower().endswith(supported_exts):
                        paths.append(os.path.join(root, f))
        self._paths = sorted(paths)

        # The window itself has no title bar to display this in, but it's
        # still what shows up in a taskbar, Alt-Tab switcher, or window
        # list — previously the title never changed from a generic
        # "Wallpaper Chooser (Prototype)", so there was no way to tell
        # which folder (or how many wallpapers) a given window was even
        # showing without checking the terminal it was launched from.
        folder_label = os.path.basename(directory.rstrip(os.sep)) or directory
        self.set_title(f"Wallpaper Chooser — {folder_label} ({len(self._paths)})")

        if not self._paths:
            print(f"No wallpapers found under {directory}; pass a directory "
                  f"with .png/.jpg/.webp files as argv[1].")
        self._empty_state.set_visible(not self._paths)

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
        say(f"Selected: {path}")

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
