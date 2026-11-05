"""Validated storage for named wallpaper collections."""

import os


COLLECTIONS_VERSION = 1
MAX_COLLECTION_NAME_LENGTH = 48


def normalize_collection_name(name):
    if not isinstance(name, str):
        raise ValueError("collection names must be strings")
    normalized = " ".join(name.split())
    if (
        not normalized
        or len(normalized) > MAX_COLLECTION_NAME_LENGTH
        or "/" in normalized
        or "\\" in normalized
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ValueError(
            f"collection names must be 1–{MAX_COLLECTION_NAME_LENGTH} characters "
            "and cannot contain path separators"
        )
    return normalized


def normalize_collections(collections):
    if not isinstance(collections, dict):
        raise ValueError("collections must be an object")
    normalized = {}
    names = set()
    for name, paths in collections.items():
        display_name = normalize_collection_name(name)
        key = display_name.casefold()
        if key in names:
            raise ValueError("collection names must be unique, ignoring case")
        if not isinstance(paths, (list, tuple)):
            raise ValueError(f"collection {display_name!r} must contain a list of paths")
        clean_paths = []
        seen_paths = set()
        for path in paths:
            if not isinstance(path, str) or not os.path.isabs(path):
                raise ValueError("collection wallpaper paths must be absolute")
            absolute = os.path.abspath(path)
            if absolute not in seen_paths:
                clean_paths.append(absolute)
                seen_paths.add(absolute)
        normalized[display_name] = clean_paths
        names.add(key)
    return dict(sorted(normalized.items(), key=lambda item: item[0].casefold()))


def encode_collections(collections):
    return {
        "version": COLLECTIONS_VERSION,
        "collections": normalize_collections(collections),
    }


def decode_collections(data):
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "collections"}
        or type(data.get("version")) is not int
        or data.get("version") != COLLECTIONS_VERSION
    ):
        raise ValueError("unsupported collections format or version")
    return normalize_collections(data["collections"])
