"""Exit-status contract for Wallmat's shell-oriented picker mode."""

SUCCESS = 0
CANCELLED = 2
INVALID_DIRECTORY = 3
SCAN_FAILED = 4


def validate_directory(directory):
    """Return an error message when a picker directory cannot be opened."""
    import os

    if not os.path.isdir(directory):
        return f"Not a directory: {directory}"
    if not os.access(directory, os.R_OK | os.X_OK):
        return f"Directory is not readable: {directory}"
    return None
