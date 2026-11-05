"""Portable, validated per-wallpaper tag storage."""

import os


TAGS_VERSION = 1
MAX_TAG_LENGTH = 40


def normalize_tags(tags):
    """Validate and de-duplicate user tags while preserving display spelling."""
    if not isinstance(tags, (list, tuple, set)):
        raise ValueError("tags must be a list of strings")
    normalized = []
    seen = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError("tag names must be strings")
        name = " ".join(tag.split())
        if (
            not name
            or len(name) > MAX_TAG_LENGTH
            or "," in name
            or any(ord(char) < 32 for char in name)
        ):
            raise ValueError(
                f"tags must be 1–{MAX_TAG_LENGTH} characters and cannot contain commas"
            )
        folded = name.casefold()
        if folded not in seen:
            normalized.append(name)
            seen.add(folded)
    return sorted(normalized, key=str.casefold)


def _is_within(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def encode_tags(tags_by_path, root):
    """Serialize tag mappings relative to root, preserving outside paths."""
    if not isinstance(tags_by_path, dict):
        raise ValueError("tag assignments must be an object")
    root = os.path.abspath(root)
    relative_paths = {}
    external_paths = {}
    for path, tags in tags_by_path.items():
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("tag paths must be absolute")
        normalized = normalize_tags(list(tags) if isinstance(tags, set) else tags)
        if not normalized:
            continue
        absolute = os.path.abspath(path)
        if _is_within(absolute, root):
            relative = os.path.relpath(absolute, root)
            if relative != os.curdir:
                relative_paths[relative] = normalized
        else:
            external_paths[absolute] = normalized
    return {
        "version": TAGS_VERSION,
        "root": root,
        "paths": dict(sorted(relative_paths.items())),
        "external_paths": dict(sorted(external_paths.items())),
    }


def decode_tags(data, current_root):
    """Load and validate a v1 tag file, rebasing paths when the source moved."""
    root = os.path.abspath(current_root)
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or data.get("version") != TAGS_VERSION
    ):
        raise ValueError("unsupported tags format or version")

    saved_root = data.get("root")
    relative_paths = data.get("paths")
    external_paths = data.get("external_paths")
    if (
        not isinstance(saved_root, str) or not saved_root or not os.path.isabs(saved_root)
        or not isinstance(relative_paths, dict)
        or not isinstance(external_paths, dict)
        or set(data) != {"version", "root", "paths", "external_paths"}
    ):
        raise ValueError("invalid tags data structure")

    saved_root = os.path.abspath(saved_root)
    resolved = {}

    for path, tags in external_paths.items():
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("external tag paths must be absolute")
        normalized = normalize_tags(tags)
        if normalized:
            resolved[os.path.abspath(path)] = set(normalized)

    for relative, tags in relative_paths.items():
        if not isinstance(relative, str) or not relative or os.path.isabs(relative):
            raise ValueError("tag paths must be non-empty relative paths")
        normalized_path = os.path.normpath(relative)
        if (
            normalized_path != relative
            or normalized_path in ("", os.curdir, os.pardir)
            or normalized_path.startswith(os.pardir + os.sep)
        ):
            raise ValueError("tag path escapes its collection root")
        normalized_tags = normalize_tags(tags)
        if not normalized_tags:
            continue
        original = os.path.abspath(os.path.join(saved_root, normalized_path))
        rebased = os.path.abspath(os.path.join(root, normalized_path))
        if saved_root == root or os.path.exists(original):
            resolved[original] = set(normalized_tags)
        elif os.path.exists(rebased) or not os.path.exists(saved_root):
            resolved[rebased] = set(normalized_tags)
        else:
            resolved[original] = set(normalized_tags)
    return resolved
