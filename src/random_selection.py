"""Helpers for avoiding recently selected wallpapers in random flows."""

import random


MAX_RANDOM_HISTORY = 20


def choose_next(candidates, recent_paths, history_limit, chooser=random.choice):
    """Choose a candidate outside the recent window, resetting when exhausted.

    Returns the chosen path and the updated, bounded history. Paths outside
    the current candidate pool are ignored so a filtered pool can be exhausted
    independently of unrelated wallpapers.
    """
    unique_candidates = list(dict.fromkeys(candidates))
    if not unique_candidates:
        return None, []

    limit = max(0, min(int(history_limit), MAX_RANDOM_HISTORY))
    if limit == 0:
        return chooser(unique_candidates), []

    candidate_set = set(unique_candidates)
    recent = [
        path for path in recent_paths
        if isinstance(path, str) and path in candidate_set
    ][:limit]
    recent_set = set(recent)
    available = [
        path for path in unique_candidates if path not in recent_set
    ]

    # Every candidate has appeared within the recent window. Start a new
    # cycle instead of getting stuck or returning an empty result.
    if not available:
        recent = []
        available = unique_candidates

    selected = chooser(available)
    updated_history = [selected] + [
        path for path in recent if path != selected
    ]
    return selected, updated_history[:limit]


def shuffle_with_recent_last(paths, recent_paths, shuffler=random.shuffle):
    """Shuffle every path while placing recently chosen items at the end."""
    shuffled = list(paths)
    shuffler(shuffled)
    recent = set(recent_paths)
    return (
        [path for path in shuffled if path not in recent]
        + [path for path in shuffled if path in recent]
    )
