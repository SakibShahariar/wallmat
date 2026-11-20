"""Time-of-day wallpaper schedule model.

Pure logic lives here so it can be tested with an injected clock. Times are
minutes since local midnight; `active_period` takes a plain integer, so
tests never need a real clock or timezone database.
"""

import json
import os
from dataclasses import dataclass

from wallpaper_scan import MAX_SCAN_DEPTH, scan_wallpapers

MAX_PERIODS = 24
SOURCE_TYPES = ("folder", "collection", "library")


def parse_clock(value: str) -> int:
    """Parse "HH:MM" into minutes since midnight."""
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("time must be HH:MM")
    try:
        hour, minute = int(value[:2]), int(value[3:])
    except ValueError as error:
        raise ValueError("time must be HH:MM") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time must be HH:MM")
    return hour * 60 + minute


def format_clock(minutes: int) -> str:
    """Format minutes since midnight as "HH:MM"."""
    if type(minutes) is not int or not 0 <= minutes < 1440:
        raise ValueError("minute must be between 0 and 1439")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class SchedulePeriod:
    name: str
    start: int
    end: int
    source_type: str
    source_value: str = ""
    enabled: bool = True

    def contains(self, minute: int) -> bool:
        """Whether a local minute falls inside this period.

        start == end means the whole day. start > end is an overnight
        period that crosses midnight.
        """
        if type(minute) is not int or not 0 <= minute < 1440:
            raise ValueError("minute must be between 0 and 1439")
        if self.start == self.end:
            return True
        if self.start < self.end:
            return self.start <= minute < self.end
        return minute >= self.start or minute < self.end

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start": format_clock(self.start),
            "end": format_clock(self.end),
            "source": self.source_type,
            "value": self.source_value,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("schedule period must be an object")
        allowed = {"name", "start", "end", "source", "value", "enabled"}
        if set(data) != allowed:
            raise ValueError("schedule period has unknown or missing fields")
        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 48:
            raise ValueError("schedule name must be 1-48 characters")
        source_type = data["source"]
        if source_type not in SOURCE_TYPES:
            raise ValueError("unsupported schedule source")
        value = data["value"]
        if not isinstance(value, str) or len(value) > 4096:
            raise ValueError("schedule source value must be a string")
        if source_type == "library" and value:
            raise ValueError("library schedules must not have a source value")
        if source_type != "library" and not value.strip():
            raise ValueError("folder/collection schedules need a source value")
        enabled = data["enabled"]
        if type(enabled) is not bool:
            raise ValueError("schedule enabled must be a boolean")
        return cls(
            name=name.strip(),
            start=parse_clock(data["start"]),
            end=parse_clock(data["end"]),
            source_type=source_type,
            source_value=value,
            enabled=enabled,
        )


def active_period(periods, minute: int):
    """Pick the matching period at a local minute, or None.

    When periods overlap, the one that has been running longest wins
    (largest circular distance from its start to `now`), with the name as
    a stable tie-break. This makes overlaps deterministic without an
    ordering dependency on the stored list.
    """
    matches = [period for period in periods if period.enabled and period.contains(minute)]
    if not matches:
        return None
    return max(
        matches,
        key=lambda period: ((minute - period.start) % 1440, period.name),
    )


def period_candidates(period, collections, folder_paths, wallpaper_dir,
                      supported_exts, scan_depth=0):
    """Resolve a period's source to existing wallpaper paths.

    Shared by the interactive app and the background daemon so both pick
    wallpapers from exactly the same sets.
    """
    if period.source_type == "library":
        return [path for path in folder_paths if os.path.isfile(path)]
    if period.source_type == "collection":
        return [path for path in collections.get(period.source_value, [])
                if os.path.isfile(path)]
    root = os.path.abspath(period.source_value)
    if not os.path.isdir(root):
        return []
    if root == os.path.abspath(wallpaper_dir or ""):
        return [path for path in folder_paths if os.path.isfile(path)]
    depth = max(0, min(int(scan_depth), MAX_SCAN_DEPTH))
    paths, _errors, _truncated = scan_wallpapers(
        root, supported_exts, max_wallpapers=10_000, max_depth=depth
    )
    return [path for path in paths if os.path.isfile(path)]


def parse_schedule(text: str) -> list[SchedulePeriod]:
    """Validate a persisted JSON schedule string."""
    if not isinstance(text, str):
        raise ValueError("schedule must be a JSON string")
    try:
        data = json.loads(text or "[]")
    except (ValueError, TypeError) as error:
        raise ValueError("schedule is not valid JSON") from error
    if not isinstance(data, list) or len(data) > MAX_PERIODS:
        raise ValueError("schedule must be a list of at most 24 periods")
    return [SchedulePeriod.from_dict(item) for item in data]


def serialize_schedule(periods) -> str:
    return json.dumps([period.to_dict() for period in periods],
                      ensure_ascii=False, separators=(",", ":"))
