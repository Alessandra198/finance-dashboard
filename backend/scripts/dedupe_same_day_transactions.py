"""
0) ``Brunch Saturday`` -> ``Brunch``; local time 10:30–15:00 (``DEMO_SEED_TIMEZONE`` / seed).
1) Exact duplicates: same user + **insights-local** calendar day + description + amount (keep lowest id).
2) Same description same **insights-local** day (any amount): keep newest ``occurred_at``; delete extras.
3) Local night 21:00–06:59 in ``resolve_insights_timezone_name()``; skips Paycheck/Rent and monthly subs.
4) Cap ``Cloud storage`` / ``Subscription`` / ``Streaming`` to 1 per **insights-local** month (prefer local day 1).
5) ``Whole Foods run``: delete rows that break a minimum 3-day gap in local dates.
6) Cap ``Gas`` to 2 rows per user per **insights-local** month (newest kept).

Uses the same timezone resolution as ``/api/insights/summary`` (``INSIGHTS_TIMEZONE`` → ``DEMO_SEED_TIMEZONE`` → ``Europe/Rome``).

All users by default. Scope with: DEDUPE_EMAIL=you@example.com

Run from backend/: PYTHONPATH=. python3 scripts/dedupe_same_day_transactions.py
"""

import os

from app.insights_timezone import resolve_insights_timezone_name
from app.transaction_dedupe import (
    cap_gas_transactions_per_utc_month,
    cap_monthly_subscription_like_rows,
    delete_nighttime_transactions,
    delete_same_day_duplicate_transactions,
    delete_same_day_same_description_keep_newest,
    delete_whole_foods_run_violating_min_local_gap,
    normalize_brunch_transactions,
)
from app.user_store import ensure_users_table, get_user_by_email


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set")
    ensure_users_table()
    email = os.getenv("DEDUPE_EMAIL", "").strip()
    uid = None
    if email:
        user = get_user_by_email(email)
        if user is None:
            raise SystemExit(f"No user {email!r}")
        uid = user.id
        label = f"{email} (user_id={user.id})"
    else:
        label = "all users"

    tz = resolve_insights_timezone_name()

    n0 = normalize_brunch_transactions(uid)
    n1 = delete_same_day_duplicate_transactions(uid, tz_name=tz)
    n2 = delete_same_day_same_description_keep_newest(uid, tz_name=tz)
    n_sub = cap_monthly_subscription_like_rows(uid, tz_name=tz, keep=1)
    n_wf = delete_whole_foods_run_violating_min_local_gap(
        uid, min_gap_days=3, tz_name=tz
    )
    n3 = delete_nighttime_transactions(tz_name=tz, user_id=uid)
    n4 = cap_gas_transactions_per_utc_month(uid, keep=2, tz_name=tz)
    print(f"Cleanup for {label} (insights TZ: {tz}):")
    print(f"  Brunch Saturday -> Brunch (10:30–15:00 local): {n0}")
    print(f"  exact same-day duplicates removed: {n1}")
    print(f"  same-day same-description (keep newest): {n2}")
    print(f"  cloud/subscription/streaming capped (1 per local month): {n_sub}")
    print(f"  whole foods min local gap (3d) enforced: {n_wf}")
    print(f"  local night ({tz}) removed (not Paycheck/Rent / subs): {n3}")
    print(f"  gas capped (max 2 per user per local month): {n4}")


if __name__ == "__main__":
    main()
