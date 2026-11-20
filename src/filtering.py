"""Pure composition of Wallmat's wallpaper filters.

Kept free of GTK imports so filter composition can be tested in the
dependency-light CI job. The GTK window applies the same ordering here as it
did before this module was extracted.
"""

import os


def apply_filters(paths, *, favorites=(), tags=None, tag=None,
                  color_family=None, palette_for=None, query="", root=""):
    """Return ``paths`` passing the active favorites/tag/color/text filters.

    Filters are applied in that order so the result is deterministic and the
    color filter composes with the other filters instead of replacing them.
    ``palette_for(path)`` returns the cached family set for a path, or None
    when no palette is available (which excludes the path from a color
    filter and leaves the wallpaper unchanged rather than failing).
    """
    result = list(paths)
    favorites = set(favorites)
    if favorites:
        result = [path for path in result if path in favorites]

    tags = tags or {}
    if tag:
        tag_key = tag.casefold()
        result = [
            path for path in result
            if any(assigned.casefold() == tag_key
                   for assigned in tags.get(path, ()))
        ]

    if color_family:
        if palette_for is None:
            result = []
        else:
            result = [
                path for path in result
                if color_family in (palette_for(path) or ())
            ]

    query = query.strip().casefold()
    if query:
        result = [
            path for path in result
            if query in os.path.basename(path).casefold()
            or query in os.path.relpath(path, root).casefold()
            or any(query in assigned.casefold()
                   for assigned in tags.get(path, ()))
        ]
    return result
