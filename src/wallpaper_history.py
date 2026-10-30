"""Persistent applied-wallpaper history helpers."""

MAX_APPLIED_HISTORY = 50


def append_applied(history, path, limit=MAX_APPLIED_HISTORY):
    """Append an applied path once, moving re-applied paths to the newest end."""
    if not isinstance(path, str) or not path:
        return list(history)[-max(0, int(limit)):] if limit else []
    bounded_limit = max(0, min(int(limit), MAX_APPLIED_HISTORY))
    if bounded_limit == 0:
        return []
    updated = [
        item for item in history
        if isinstance(item, str) and item and item != path
    ]
    updated.append(path)
    return updated[-bounded_limit:]


def for_collection(history, available_paths, limit=MAX_APPLIED_HISTORY):
    """Return the newest existing history entries belonging to one collection."""
    available = set(available_paths)
    bounded_limit = max(0, min(int(limit), MAX_APPLIED_HISTORY))
    if bounded_limit == 0:
        return []
    return [
        path for path in history
        if isinstance(path, str) and path in available
    ][-bounded_limit:]
