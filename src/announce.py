"""Central stdout announce channel for the wallpaper chooser.

All UI feedback lines (Focus:/Selected:/CSS diagnostics) route through
``say()`` so the whole app can be silenced with ``set_quiet(True)``.
That's how ``--plain`` mode guarantees stdout carries ONLY the final
wallpaper path (drop-in contract for the matugen.fish pipeline, which
captures stdout via fish command substitution).
"""

_quiet = False


def set_quiet(flag: bool):
    global _quiet
    _quiet = flag


def say(message: str):
    if not _quiet:
        print(message)