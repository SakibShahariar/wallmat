"""Small, display-oriented helpers shared by accessible wallpaper widgets."""

import os


def wallpaper_accessible_name(path):
    """Return a concise filename label with its parent folder for context."""
    if not isinstance(path, str) or not path:
        return "Wallpaper thumbnail"
    filename = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    if parent:
        return f"{filename}, in {parent}"
    return filename or "Wallpaper thumbnail"
