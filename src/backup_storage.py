"""Versioned, validated JSON backups for Wallmat user data."""

from favorites_storage import decode_favorites, encode_favorites
from tags_storage import decode_tags, encode_tags
from collections_storage import decode_collections, encode_collections


BACKUP_FORMAT = "dev.sakib.Wallmat.backup"
BACKUP_VERSION = 3

# Keep this allow-list aligned with data/dev.sakib.Wallmat.gschema.xml.
# It intentionally excludes transient state and unknown future settings.
_STRING_SETTINGS = {
    "selected-layout",
    "last-filter",
    "sort-mode",
    "last-wallpaper-folder",
    "selected-wallpaper",
}
_BOOLEAN_SETTINGS = {"favorites-only"}
_INTEGER_SETTINGS = {
    "auto-rotate-interval": (60, 1800),
    "random-history-limit": (0, 20),
    "scan-depth": (0, 20),
}
_STRING_LIST_SETTINGS = {
    "recent-random-wallpapers",
    "applied-wallpaper-history",
    "recent-wallpapers",
}
_ALLOWED_LAYOUTS = {
    "split_screen", "stacked_deck", "infinite_ribbon", "masonry_grid",
    "glassmorphism", "parallax_gallery", "radial_fan", "cylindrical_ring",
}
_ALLOWED_SORTS = {"name", "newest", "oldest", "resolution", "random", "folder"}


def validate_preferences(preferences):
    """Return a validated copy of a partial GSettings preference mapping."""
    if not isinstance(preferences, dict):
        raise ValueError("preferences must be a JSON object")

    allowed = (
        _STRING_SETTINGS
        | _BOOLEAN_SETTINGS
        | set(_INTEGER_SETTINGS)
        | _STRING_LIST_SETTINGS
    )
    unknown = set(preferences) - allowed
    if unknown:
        raise ValueError(f"unknown preference key(s): {', '.join(sorted(unknown))}")

    validated = {}
    for key, value in preferences.items():
        if key in _STRING_SETTINGS:
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
            if key == "selected-layout" and value not in _ALLOWED_LAYOUTS:
                raise ValueError("selected-layout is not a supported layout")
            if key == "sort-mode" and value not in _ALLOWED_SORTS:
                raise ValueError("sort-mode is not supported")
        elif key in _BOOLEAN_SETTINGS:
            if type(value) is not bool:
                raise ValueError(f"{key} must be a boolean")
        elif key in _INTEGER_SETTINGS:
            minimum, maximum = _INTEGER_SETTINGS[key]
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(
                    f"{key} must be an integer from {minimum} to {maximum}"
                )
            if key == "auto-rotate-interval" and value not in {60, 300, 600, 1800}:
                raise ValueError("auto-rotate-interval is not a supported interval")
        elif key in _STRING_LIST_SETTINGS:
            if (
                not isinstance(value, list)
                or any(not isinstance(item, str) for item in value)
            ):
                raise ValueError(f"{key} must be a list of strings")
        validated[key] = list(value) if key in _STRING_LIST_SETTINGS else value
    return validated


def encode_backup(favorites, wallpaper_root, preferences, tags=None, collections=None):
    """Build a JSON-compatible backup without mutating application state."""
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "favorites": encode_favorites(favorites, wallpaper_root),
        "tags": encode_tags({} if tags is None else tags, wallpaper_root),
        "collections": encode_collections({} if collections is None else collections),
        "preferences": validate_preferences(preferences),
    }


def decode_backup(data, current_root):
    """Validate a complete backup before returning data ready to apply."""
    if not isinstance(data, dict):
        raise ValueError("backup must be a JSON object")
    if data.get("format") != BACKUP_FORMAT:
        raise ValueError("file is not a Wallmat backup")
    version = data.get("version")
    if type(version) is not int or version not in (1, BACKUP_VERSION):
        raise ValueError("unsupported Wallmat backup version")
    expected_fields = {"format", "version", "favorites", "preferences"}
    if version >= 2:
        expected_fields.add("tags")
    if version >= 3:
        expected_fields.add("collections")
    if set(data) != expected_fields:
        raise ValueError("backup contains missing or unexpected top-level fields")

    # Validate every section before callers write any current user data.
    favorites = decode_favorites(data["favorites"], current_root)
    preferences = validate_preferences(data["preferences"])
    tags = decode_tags(data["tags"], current_root) if version >= 2 else None
    collections = decode_collections(data["collections"]) if version >= 3 else None
    return {
        "favorites": favorites,
        "preferences": preferences,
        "tags": tags,
        "collections": collections,
    }
