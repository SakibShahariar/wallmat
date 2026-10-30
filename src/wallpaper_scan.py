"""Deterministic wallpaper directory scanning with safe symlink handling."""

import os


class ScanCancelled(Exception):
    """Raised when a caller cancels an in-progress directory scan."""


MAX_SCAN_DEPTH = 20


def scan_wallpapers(directory, supported_extensions, max_wallpapers=10_000,
                    max_depth=0, cancellation_event=None, progress_callback=None):
    """Return (paths, errors, truncated) for a wallpaper directory.

    Depth zero means unlimited recursion; depth one scans only the root
    directory. Symlinked files and directories are deliberately skipped.
    """
    paths = []
    errors = []
    seen_paths = set()
    truncated = False
    extensions = tuple(
        extension.lower() if extension.startswith(".")
        else f".{extension.lower()}"
        for extension in supported_extensions
    )
    try:
        depth_limit = int(max_depth)
    except (TypeError, ValueError):
        depth_limit = 0
    depth_limit = max(0, min(depth_limit, MAX_SCAN_DEPTH))

    if not os.path.isdir(directory):
        errors.append(
            f"{directory}: not an accessible directory; check that it "
            "exists and that you have permission to read it"
        )
        return paths, errors, truncated

    def record_error(error):
        error_path = error.filename or directory
        detail = error.strerror or str(error)
        errors.append(f"{error_path}: {detail}")

    for root, dirs, files in os.walk(
        directory, topdown=True, onerror=record_error, followlinks=False
    ):
        if cancellation_event is not None and cancellation_event.is_set():
            raise ScanCancelled("Wallpaper scan was cancelled")
        dirs.sort()
        files.sort()

        # Do not descend into directory symlinks, even if they point back
        # into the tree or form a cycle.
        dirs[:] = [
            name for name in dirs
            if not os.path.islink(os.path.join(root, name))
        ]

        relative_root = os.path.relpath(root, directory)
        depth = 0 if relative_root == "." else relative_root.count(os.sep) + 1
        if depth_limit and depth + 1 >= depth_limit:
            dirs[:] = []

        for name in files:
            if cancellation_event is not None and cancellation_event.is_set():
                raise ScanCancelled("Wallpaper scan was cancelled")
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            if not name.lower().endswith(extensions):
                continue
            identity = os.path.realpath(path)
            if identity in seen_paths:
                continue
            seen_paths.add(identity)
            paths.append(path)
            if progress_callback is not None and len(paths) % 50 == 0:
                progress_callback(len(paths))
            if len(paths) >= max_wallpapers:
                truncated = True
                break
        if truncated:
            break

    if progress_callback is not None:
        progress_callback(len(paths))
    return paths, errors, truncated
