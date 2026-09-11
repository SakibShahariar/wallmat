"""
WallLayout: abstract base class every layout implements.

Layouts are built lazily — a layout's build() is only called the first
time the user switches to it, not at app startup (per spec section 7).
Once built, the widget is cached and reused on subsequent switches so
state (scroll position, selection) survives.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject


class WallLayout(GObject.Object):
    """
    Subclasses must implement build() and should emit 'wallpaper-selected'
    when the user picks an image (via self.emit("wallpaper-selected", path)).
    """

    __gsignals__ = {
        "wallpaper-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    # Human-readable name shown in the layout switcher popover
    display_name: str = "Unnamed Layout"
    # Rough perf tier from the spec, surfaced in the UI as a hint/warning
    performance_tier: str = "unknown"  # "fast" | "medium" | "slow"

    def __init__(self):
        super().__init__()
        self._widget: Gtk.Widget | None = None
        self._paths: list[str] = []

    def get_widget(self) -> Gtk.Widget:
        """Builds the layout on first access, returns cached widget after."""
        if self._widget is None:
            self._widget = self.build()
            if self._paths:
                self.load_wallpapers(self._paths)
        return self._widget

    def is_built(self) -> bool:
        return self._widget is not None

    def load_wallpapers(self, paths: list[str]):
        """Called whenever the wallpaper set changes. Safe to call before
        the layout is built — paths are cached and applied on first build."""
        self._paths = paths
        if self._widget is not None:
            self._apply_wallpapers(paths)

    def build(self) -> Gtk.Widget:
        """Construct and return the root widget for this layout."""
        raise NotImplementedError

    def _apply_wallpapers(self, paths: list[str]):
        """Populate the already-built widget with the given image paths."""
        raise NotImplementedError

    def on_activate(self):
        """Called each time the user switches TO this layout. Optional override."""
        pass

    def on_deactivate(self):
        """Called each time the user switches AWAY from this layout. Optional
        override — good place to pause animations/timers you don't need
        while off-screen."""
        pass
