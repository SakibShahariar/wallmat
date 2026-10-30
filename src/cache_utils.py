"""Bounded thumbnail-cache maintenance helpers."""

import os


DEFAULT_CACHE_LIMIT_BYTES = 512 * 1024 * 1024
CACHE_EXTENSIONS = (".png", ".webp")


def prune_cache_directory(directory, max_bytes=DEFAULT_CACHE_LIMIT_BYTES):
    """Remove least-recently-used cache files until the directory fits.

    Only regular PNG/WebP cache files are eligible. Other files and symlinks
    are left untouched. Returns (remaining_bytes, removed_paths).
    """
    entries = []
    total_bytes = 0
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if not entry.name.lower().endswith(CACHE_EXTENSIONS):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                entries.append((stat.st_mtime_ns, entry.path, stat.st_size))
                total_bytes += stat.st_size
    except OSError:
        return 0, []

    removed = []
    limit = max(0, int(max_bytes))
    for _modified, path, size in sorted(entries):
        if total_bytes <= limit:
            break
        try:
            os.unlink(path)
        except OSError:
            continue
        total_bytes -= size
        removed.append(path)

    return total_bytes, removed
