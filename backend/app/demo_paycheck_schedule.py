"""
Demo recurring transactions (UTC):
- Paycheck: last day of month at 09:05
- Rent: 1st of month at 10:00

Repair helpers dedupe duplicates (same user + same UTC month), realign dates, and normalize amounts.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone

from .demo_identity import is_demo_primary_user_email
from .insights_timezone import resolve_insights_timezone_name

PAYCHECK_HOUR = 9
PAYCHECK_MINUTE = 5
RENT_HOUR = 10
RENT_MINUTE = 0

# Canonical demo amounts (keep in sync with seed scripts).
DEMO_PAYCHECK_CENTS = 275_000
DEMO_RENT_CENTS = -125_000
# scripts/seed_nov_2025.py FEB_EXTRA_INCOME_CENTS — idempotent repair insert for existing DBs.
FEB_2026_DEMO_REWARDS_CENTS = 140_000


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def paycheck_at_month(year: int, month: int) -> datetime:
    return datetime(
        year,
        month,
        last_day_of_month(year, month),
        PAYCHECK_HOUR,
        PAYCHECK_MINUTE,
        tzinfo=timezone.utc,
    )


def realign_paychecks_to_month_end(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
) -> int:
    """
    Set every matching Paycheck row's occurred_at to the last **insights-local** calendar day of
    that row's bucket month at 09:05 UTC (same convention as seeds).

    description match: LOWER(TRIM(description)) = 'paycheck'
    """
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    sql = """
    UPDATE transactions AS t
    SET occurred_at = (
      (
        ((date_trunc('month', t.occurred_at AT TIME ZONE %s) + interval '1 month' - interval '1 day')::date)
        + interval '9 hours 5 minutes'
      ) AT TIME ZONE 'UTC'
    )
    WHERE LOWER(TRIM(t.description)) = 'paycheck'
    """
    params: list[object] = [tz]
    if user_id is not None:
        sql += " AND t.user_id = %s"
        params.append(user_id)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            updated = cur.rowcount
        conn.commit()
    return int(updated)


def realign_rent_to_first_of_month(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
) -> int:
    """Set Rent rows to 10:00 UTC on the 1st of the **insights-local** month of occurred_at."""
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    sql = """
    UPDATE transactions AS t
    SET occurred_at = (
      (
        (date_trunc('month', t.occurred_at AT TIME ZONE %s)::date)
        + interval '10 hours'
      ) AT TIME ZONE 'UTC'
    )
    WHERE LOWER(TRIM(t.description)) = 'rent'
    """
    params: list[object] = [tz]
    if user_id is not None:
        sql += " AND t.user_id = %s"
        params.append(user_id)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            updated = cur.rowcount
        conn.commit()
    return int(updated)


def _dedupe_one_per_insights_month(
    *,
    description_lc: str,
    preferred_amount_cents: int,
    user_id: int | None,
    tz_name: str,
) -> int:
    """Keep one row per (user_id, insights-local calendar month); prefer amount, then highest id."""
    from .db import connect

    base = """
    DELETE FROM transactions
    WHERE id IN (
      SELECT id FROM (
        SELECT id,
          ROW_NUMBER() OVER (
            PARTITION BY user_id,
              date_trunc('month', occurred_at AT TIME ZONE %s)
            ORDER BY
              CASE WHEN amount_cents = %s THEN 0 ELSE 1 END,
              id DESC
          ) AS rn
        FROM transactions
        WHERE LOWER(TRIM(description)) = %s
    """
    params: list[object] = [tz_name, preferred_amount_cents, description_lc]
    if user_id is not None:
        base += " AND user_id = %s"
        params.append(user_id)
    base += """
      ) sub WHERE rn > 1
    )
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(base, params)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def dedupe_paychecks_per_month(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
) -> int:
    return _dedupe_one_per_insights_month(
        description_lc="paycheck",
        preferred_amount_cents=DEMO_PAYCHECK_CENTS,
        user_id=user_id,
        tz_name=tz_name or resolve_insights_timezone_name(),
    )


def dedupe_rent_per_month(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
) -> int:
    return _dedupe_one_per_insights_month(
        description_lc="rent",
        preferred_amount_cents=DEMO_RENT_CENTS,
        user_id=user_id,
        tz_name=tz_name or resolve_insights_timezone_name(),
    )


def normalize_demo_recurring_amounts(user_id: int) -> tuple[int, int]:
    """Set Paycheck / Rent amounts to demo canonical values for this user only."""
    from .db import connect

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transactions SET amount_cents = %s
                WHERE user_id = %s AND LOWER(TRIM(description)) = 'paycheck'
                """,
                (DEMO_PAYCHECK_CENTS, user_id),
            )
            pc = cur.rowcount
            cur.execute(
                """
                UPDATE transactions SET amount_cents = %s
                WHERE user_id = %s AND LOWER(TRIM(description)) = 'rent'
                """,
                (DEMO_RENT_CENTS, user_id),
            )
            rt = cur.rowcount
        conn.commit()
    return int(pc), int(rt)


def monthly_recurring_exists(
    user_id: int,
    *,
    occurred_at: datetime,
    description: str,
    tz_name: str | None = None,
) -> bool:
    """True if this user already has a row with same description in the same insights-local month."""
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM transactions
                WHERE user_id = %s
                  AND LOWER(TRIM(description)) = LOWER(TRIM(%s))
                  AND date_trunc('month', occurred_at AT TIME ZONE %s)
                      = date_trunc('month', %s AT TIME ZONE %s)
                LIMIT 1
                """,
                (user_id, description, tz, occurred_at, tz),
            )
            return cur.fetchone() is not None


def ensure_demo_february_rewards_payout(user_id: int | None = None) -> int:
    """
    If the demo account is missing the Feb 2026 ``Rewards payout (demo)`` inflow, insert it.
    Keeps the savings-rate chart green for February without a full re-seed. No-op for other users.
    """
    from .db import connect
    from .user_store import get_user_by_id

    if user_id is None:
        return 0
    user = get_user_by_id(user_id)

    if user is None or not is_demo_primary_user_email(user.email):
        return 0

    tz_name = resolve_insights_timezone_name()
    desc = "Rewards payout (demo)"
    occurred_at = datetime(2026, 2, 24, 13, 10, tzinfo=timezone.utc)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM transactions
                WHERE user_id = %s
                  AND description = %s
                  AND (date_trunc('month', occurred_at AT TIME ZONE %s))::date = DATE '2026-02-01'
                LIMIT 1
                """,
                (user_id, desc, tz_name),
            )
            if cur.fetchone() is not None:
                return 0
            cur.execute(
                """
                INSERT INTO transactions (user_id, category_id, amount_cents, description, occurred_at)
                VALUES (%s, NULL, %s, %s, %s)
                """,
                (user_id, FEB_2026_DEMO_REWARDS_CENTS, desc, occurred_at),
            )
        conn.commit()
    return 1


def repair_recurring_demo_data(user_id: int | None = None) -> dict[str, int]:
    """
    Realign Paycheck/Rent, monthly dedupe, normalize amounts, then:
    Brunch Saturday -> Brunch (10:30–15:00 local), exact same-day dupes, same-day same-description
    (keep newest), cap subscription-like rows to 1 per insights-local month (prefer local day 1),
    trim Whole Foods run to min 3-day local gaps, local-night purge, cap Gas to 2 per insights-local month.

    Uses ``resolve_insights_timezone_name()`` for all month/day bucketing (same as ``/api/insights/summary``).
    """
    from .transaction_dedupe import (
        cap_gas_transactions_per_utc_month,
        cap_monthly_subscription_like_rows,
        delete_nighttime_transactions,
        delete_same_day_duplicate_transactions,
        delete_same_day_same_description_keep_newest,
        delete_whole_foods_run_violating_min_local_gap,
        normalize_brunch_transactions,
    )

    tz = resolve_insights_timezone_name()

    out: dict[str, int] = {}
    out["paychecks_realigned"] = realign_paychecks_to_month_end(user_id, tz_name=tz)
    out["rent_realigned"] = realign_rent_to_first_of_month(user_id, tz_name=tz)
    out["paychecks_deduped"] = dedupe_paychecks_per_month(user_id, tz_name=tz)
    out["rent_deduped"] = dedupe_rent_per_month(user_id, tz_name=tz)
    if user_id is not None:
        np, nr = normalize_demo_recurring_amounts(user_id)
    else:
        np, nr = 0, 0
    out["paychecks_amount_normalized"] = np
    out["rent_amount_normalized"] = nr
    out["brunch_normalized"] = normalize_brunch_transactions(user_id)
    out["same_day_exact_duplicates_deleted"] = delete_same_day_duplicate_transactions(
        user_id, tz_name=tz
    )
    out["same_day_same_desc_deleted"] = delete_same_day_same_description_keep_newest(
        user_id, tz_name=tz
    )
    out["subscription_like_capped_per_utc_month"] = cap_monthly_subscription_like_rows(
        user_id,
        tz_name=tz,
        keep=1,
    )
    out["whole_foods_min_gap_deleted"] = delete_whole_foods_run_violating_min_local_gap(
        user_id,
        min_gap_days=3,
        tz_name=tz,
    )
    out["nighttime_local_deleted"] = delete_nighttime_transactions(
        tz_name=tz,
        user_id=user_id,
    )
    out["gas_capped_per_utc_month"] = cap_gas_transactions_per_utc_month(
        user_id, keep=2, tz_name=tz
    )
    out["february_demo_rewards_inserted"] = ensure_demo_february_rewards_payout(user_id)
    return out
