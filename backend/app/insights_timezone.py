"""
Single source of truth for the IANA timezone name used for insights ranges, monthly buckets,
and demo repair/dedupe alignment (see code review: avoid mixing UTC vs local months).
"""

from __future__ import annotations

import os


def resolve_insights_timezone_name() -> str:
    """
    Same resolution order as insights summaries: explicit insights TZ, then demo seed TZ, then Rome.

    Set ``INSIGHTS_TIMEZONE=UTC`` for strict UTC months everywhere.
    """
    return os.getenv("INSIGHTS_TIMEZONE") or os.getenv("DEMO_SEED_TIMEZONE") or "Europe/Rome"
