"""Portable favorites serialization with legacy-list migration."""

import os


FAVORITES_VERSION = 1


def _is_within(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def decode_favorites(data, current_root):
    """Load v1 relative favorites or legacy absolute-path arrays.

    If a saved collection root disappeared, relative entries are rebased to
    the currently selected root. If the old root still exists, its absolute
    paths remain authoritative so switching between unrelated folders does
    not silently retarget favorites.
    """
    root = os.path.abspath(current_root)
    if isinstance(data, list):
        if any(not isinstance(path, str) or not os.path.isabs(path) for path in data):
            raise ValueError("legacy favorites must contain absolute paths")
        return set(data)

    if not isinstance(data, dict) or data.get("version") != FAVORITES_VERSION:
        raise ValueError("unsupported favorites format or version")

    saved_root = data.get("root")
    relative_paths = data.get("paths")
    external_paths = data.get("external_paths", [])
    if (
        not isinstance(saved_root, str) or not saved_root
        or not isinstance(relative_paths, list)
        or not isinstance(external_paths, list)
        or any(not isinstance(path, str) for path in relative_paths)
        or any(not isinstance(path, str) or not os.path.isabs(path)
               for path in external_paths)
    ):
        raise ValueError("invalid favorites data structure")

    resolved = set(external_paths)
    saved_root = os.path.abspath(saved_root)
    for relative in relative_paths:
        if not relative or os.path.isabs(relative):
            raise ValueError("favorite paths must be non-empty relative paths")
        normalized = os.path.normpath(relative)
        if normalized == os.pardir or normalized.startswith(os.pardir + os.sep):
            raise ValueError("favorite path escapes its collection root")
        original = os.path.abspath(os.path.join(saved_root, normalized))
        rebased = os.path.abspath(os.path.join(root, normalized))
        if saved_root == root or os.path.exists(saved_root) or not os.path.exists(rebased):
            resolved.add(original)
        else:
            resolved.add(rebased)
    return resolved


def encode_favorites(paths, root):
    """Serialize paths relative to root, preserving favorites outside it."""
    root = os.path.abspath(root)
    relative_paths = []
    external_paths = []
    for path in sorted(set(paths)):
        absolute = os.path.abspath(path)
        if _is_within(absolute, root):
            relative = os.path.relpath(absolute, root)
            if relative != os.curdir:
                relative_paths.append(relative)
        else:
            external_paths.append(absolute)
    return {
        "version": FAVORITES_VERSION,
        "root": root,
        "paths": relative_paths,
        "external_paths": external_paths,
    }
