"""Backend-neutral wallpaper placement modes and GNOME mapping."""

MODES = ("fill", "fit", "center", "stretch")
MODE_LABELS = {
    "fill": "Fill / crop",
    "fit": "Fit (keep aspect)",
    "center": "Center (original size)",
    "stretch": "Stretch",
}

# org.gnome.desktop.background picture-options values. These are the
# actual enum strings exposed by GNOME; other desktops may expose none.
GNOME_OPTIONS = {
    "fill": "zoom",
    "fit": "scaled",
    "center": "centered",
    "stretch": "stretched",
}


def gnome_option(mode: str) -> str | None:
    """Return the GNOME picture-options value for a mode, if supported."""
    return GNOME_OPTIONS.get(mode)


def supported_modes(available_options) -> set[str]:
    """Which modes a desktop's picture-options enum can express."""
    available = set(available_options or ())
    return {
        mode for mode, option in GNOME_OPTIONS.items() if option in available
    }


def apply_gnome_placement(settings, mode: str, background: str = "#000000") -> bool:
    """Apply a placement mode through GNOME's background settings.

    Returns False when the desktop does not expose a mapping for the mode.
    The source image is never modified.
    """
    option = gnome_option(mode)
    if option is None:
        return False
    keys = settings.list_keys()
    if "picture-options" not in keys or option not in settings.get_range(
            "picture-options")[1]:
        return False
    settings.set_string("picture-options", option)
    if mode in ("fit", "center"):
        if "color-shading-type" in keys:
            settings.set_string("color-shading-type", "solid")
        if "primary-color" in keys:
            try:
                settings.set_string("primary-color", background)
            except Exception:
                pass
    return True
