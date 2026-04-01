"""
Random transaction timestamps for seed data: wall time between 07:00 and 20:59 in a
configurable timezone (no 21:00–06:59 local), stored as UTC.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def seed_timezone() -> ZoneInfo:
    name = os.getenv("DEMO_SEED_TIMEZONE", "Europe/Rome")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def random_occurred_at(rng: random.Random, year: int, month: int, day: int) -> datetime:
    """07:00–20:59 local in seed TZ, returned as timezone-aware UTC."""
    tz = seed_timezone()
    h = rng.randint(7, 20)
    m = rng.randint(0, 59)
    local = datetime(year, month, day, h, m, tzinfo=tz)
    return local.astimezone(timezone.utc)


def random_brunch_time(rng: random.Random, year: int, month: int, day: int) -> datetime:
    """Local wall time 10:30–15:00 inclusive in seed TZ, returned as UTC."""
    tz = seed_timezone()
    min_min = 10 * 60 + 30  # 10:30
    max_min = 15 * 60  # 15:00
    total = rng.randint(min_min, max_min)
    h, m = divmod(total, 60)
    local = datetime(year, month, day, h, m, tzinfo=tz)
    return local.astimezone(timezone.utc)
