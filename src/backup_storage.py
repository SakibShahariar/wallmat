"""Versioned, validated JSON backups for Wallmat user data."""

import json

from favorites_storage import decode_favorites, encode_favorites
from tags_storage import decode_tags, encode_tags
from collections_storage import decode_collections, encode_collections
from schedule import parse_schedule, serialize_schedule
from placement import MODES


BACKUP_FORMAT = "dev.sakib.Wallmat.backup"
BACKUP_VERSION = 3

# Sections a user may choose to include in an export. Order is stable so
# backups remain diffable and the section list is easy to read.
BACKUP_SECTIONS = ("favorites", "tags", "collections", "preferences")

# Keep this allow-list aligned with data/dev.sakib.Wallmat.gschema.xml.
# It intentionally excludes transient state and unknown future settings.
_STRING_SETTINGS = {
    "selected-layout",
    "last-filter",
    "sort-mode",
    "last-wallpaper-folder",
    "selected-wallpaper",
    "matugen-args",
    "wallpaper-target",
    "seamless-backdrop",
    "rotation-schedule",
    "layout-positions",
    "wallpaper-placement",
    "placement-background",
}
_BOOLEAN_SETTINGS = {"favorites-only", "seamless-mode"}
_INTEGER_SETTINGS = {
    "auto-rotate-interval": (60, 1800),
    "random-history-limit": (0, 20),
    "scan-depth": (0, 20),
    "thumbnail-cache-limit-mb": (64, 4096),
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
_ALLOWED_TARGETS = {"desktop", "lock", "both"}
_ALLOWED_BACKDROPS = {"transparent", "blurred"}


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
            if key == "wallpaper-target" and value not in _ALLOWED_TARGETS:
                raise ValueError("wallpaper-target is not supported")
            if key == "seamless-backdrop" and value not in _ALLOWED_BACKDROPS:
                raise ValueError("seamless-backdrop is not supported")
            if key == "rotation-schedule":
                try:
                    value = serialize_schedule(parse_schedule(value))
                except ValueError as error:
                    raise ValueError(f"rotation-schedule is invalid: {error}") from error
            if key == "wallpaper-placement" and value not in MODES:
                raise ValueError("wallpaper-placement is not a supported mode")
            if key == "placement-background":
                if not isinstance(value, str) or len(value) > 64:
                    raise ValueError("placement-background must be a short color string")
            if key == "layout-positions":
                try:
                    positions = json.loads(value)
                except (TypeError, ValueError) as error:
                    raise ValueError("layout-positions is not valid JSON") from error
                if not isinstance(positions, dict) or any(
                    not isinstance(name, str) or type(index) is not int or index < 0
                    for name, index in positions.items()
                ):
                    raise ValueError("layout-positions must map names to indices")
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


def encode_backup(favorites, wallpaper_root, preferences, tags=None, collections=None,
                  sections=None):
    """Build a JSON-compatible backup without mutating application state.

    ``sections`` optionally limits which data sections are included; omitted
    sections are written as null and listed in ``sections`` so a restore knows
    not to replace the user's current data for them. The default includes all
    sections and keeps the original on-disk shape for compatibility.
    """
    if sections is not None:
        names = list(sections)
        if len(set(names)) != len(names):
            raise ValueError("sections must not contain duplicates")
    else:
        names = list(BACKUP_SECTIONS)
    selected = set(names)
    if not selected or not selected.issubset(BACKUP_SECTIONS):
        raise ValueError("sections must be a non-empty subset of the backup sections")
    data = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "favorites": encode_favorites(favorites, wallpaper_root),
        "tags": encode_tags({} if tags is None else tags, wallpaper_root),
        "collections": encode_collections({} if collections is None else collections),
        "preferences": validate_preferences(preferences),
    }
    if len(selected) == len(BACKUP_SECTIONS):
        return data
    for section in BACKUP_SECTIONS:
        if section not in selected:
            data[section] = None
    data["sections"] = [section for section in BACKUP_SECTIONS if section in selected]
    return data


def decode_backup(data, current_root):
    """Validate a complete backup before returning data ready to apply."""
    if not isinstance(data, dict):
        raise ValueError("backup must be a JSON object")
    if data.get("format") != BACKUP_FORMAT:
        raise ValueError("file is not a Wallmat backup")
    version = data.get("version")
    if type(version) is not int or version not in (1, 2, BACKUP_VERSION):
        raise ValueError("unsupported Wallmat backup version")
    expected_fields = {"format", "version", "favorites", "preferences"}
    if version >= 2:
        expected_fields.add("tags")
    if version >= 3:
        expected_fields.add("collections")
    has_sections = version >= 3 and "sections" in data
    allowed_fields = set(expected_fields) | ({"sections"} if has_sections else set())
    if set(data) != allowed_fields:
        raise ValueError("backup contains missing or unexpected top-level fields")

    if has_sections:
        names = data["sections"]
        if (
            not isinstance(names, list) or not names
            or any(name not in BACKUP_SECTIONS for name in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("backup sections are invalid")
        included = set(names)
    else:
        included = set(expected_fields) & set(BACKUP_SECTIONS)

    # Validate every included section before callers write any current data.
    def section_value(name):
        return data.get(name) if name in included else None

    favorites_data = section_value("favorites")
    preferences_data = section_value("preferences")
    tags_data = section_value("tags")
    collections_data = section_value("collections")
    if favorites_data is not None and not isinstance(favorites_data, (list, dict)):
        raise ValueError("favorites must be a list or object")
    if preferences_data is not None and not isinstance(preferences_data, dict):
        raise ValueError("preferences must be an object")
    if tags_data is not None and not isinstance(tags_data, (list, dict)):
        raise ValueError("tags must be a list or object")
    if collections_data is not None and not isinstance(collections_data, dict):
        raise ValueError("collections must be an object")

    favorites = decode_favorites(favorites_data, current_root) if favorites_data is not None else None
    preferences = validate_preferences(preferences_data) if preferences_data is not None else None
    tags = decode_tags(tags_data, current_root) if tags_data is not None else None
    collections = decode_collections(collections_data) if collections_data is not None else None
    return {
        "favorites": favorites,
        "preferences": preferences,
        "tags": tags,
        "collections": collections,
    }
