"""Pure sorting helpers for wallpaper collections."""


def sort_by_resolution(paths, dimension_getter):
    """Sort largest pixel area first without decoding full image contents.

    Unknown or unreadable dimensions are kept at the end. Equal-sized images
    use their path as a stable, case-insensitive tie-breaker.
    """
    def key(path):
        try:
            dimensions = dimension_getter(path)
            width, height = dimensions if dimensions else (0, 0)
            width, height = int(width), int(height)
        except (OSError, TypeError, ValueError):
            width, height = 0, 0

        if width <= 0 or height <= 0:
            return (1, 0, 0, 0, path.casefold())
        return (0, -(width * height), -width, -height, path.casefold())

    return sorted(paths, key=key)
