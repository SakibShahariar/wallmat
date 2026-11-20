"""Tests for the time-of-day schedule model with an injected clock."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from schedule import (
    SchedulePeriod, active_period, format_clock, parse_clock,
    parse_schedule, serialize_schedule,
)


def period(name, start, end, source="library", value="", enabled=True):
    return SchedulePeriod(name, parse_clock(start), parse_clock(end),
                          source, value, enabled)


class ScheduleTests(unittest.TestCase):
    def test_clock_roundtrip_and_validation(self):
        self.assertEqual(parse_clock("09:05"), 545)
        self.assertEqual(format_clock(545), "09:05")
        for bad in ("9:05", "25:00", "12:60", "1234", None):
            with self.assertRaises(ValueError):
                parse_clock(bad)

    def test_regular_period_boundaries(self):
        p = period("day", "09:00", "17:00")
        self.assertFalse(p.contains(539))
        self.assertTrue(p.contains(540))
        self.assertTrue(p.contains(1019))
        self.assertFalse(p.contains(1020))

    def test_overnight_period_crosses_midnight(self):
        p = period("night", "22:00", "06:00")
        self.assertTrue(p.contains(1320))
        self.assertTrue(p.contains(0))
        self.assertFalse(p.contains(360))
        self.assertTrue(p.contains(359))

    def test_full_day_period(self):
        p = period("all", "12:00", "12:00")
        self.assertTrue(p.contains(0))
        self.assertTrue(p.contains(1439))

    def test_active_period_uses_injected_clock(self):
        periods = [period("night", "22:00", "06:00"), period("day", "08:00", "17:00")]
        self.assertEqual(active_period(periods, 600).name, "day")
        self.assertEqual(active_period(periods, 0).name, "night")
        self.assertIsNone(active_period(periods, 420))

    def test_overlap_is_deterministic(self):
        periods = [period("early", "06:00", "18:00"), period("late", "10:00", "20:00")]
        self.assertEqual(active_period(periods, 720).name, "early")
        self.assertEqual(active_period(list(reversed(periods)), 720).name, "early")

    def test_disabled_period_is_ignored(self):
        p = period("off", "00:00", "23:59", enabled=False)
        self.assertIsNone(active_period([p], 720))

    def test_dst_and_timezone_use_local_wall_clock(self):
        # A zone-offset conversion must not shift the wall-clock minute.
        utc = datetime(2026, 11, 19, 23, 30, tzinfo=ZoneInfo("UTC"))
        local = utc.astimezone(ZoneInfo("Asia/Dhaka"))
        minute = local.hour * 60 + local.minute
        self.assertEqual(minute, 5 * 60 + 30)  # next day, 05:30 local
        p = period("night", "22:00", "06:00")
        self.assertTrue(p.contains(minute))

    def test_persistence_roundtrip_and_validation(self):
        periods = [period("day", "08:00", "17:00", "collection", "Favorites")]
        restored = parse_schedule(serialize_schedule(periods))
        self.assertEqual(restored, periods)
        with self.assertRaises(ValueError):
            parse_schedule("{not json")
        with self.assertRaises(ValueError):
            SchedulePeriod.from_dict({"name": "x", "start": "09:00", "end": "10:00",
                                      "source": "folder", "value": "", "enabled": True})


if __name__ == "__main__":
    unittest.main()
