"""
Remove duplicate transactions and apply demo cleanup rules.

**Timezone model:** Unless noted, "same day" and "per month" use the same IANA zone as insights
(``resolve_insights_timezone_name()``: ``INSIGHTS_TIMEZONE``, then ``DEMO_SEED_TIMEZONE``, then
``Europe/Rome``). Set ``INSIGHTS_TIMEZONE=UTC`` for strict UTC everywhere.
"""

from __future__ import annotations

from .insights_timezone import resolve_insights_timezone_name


def delete_same_day_duplicate_transactions(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
) -> int:
    """
    Delete extra rows that are exact duplicates on the same **local calendar day** in ``tz_name``.

    :param user_id: Limit to this user, or None for all users.
    :return: Number of rows deleted.
    """
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    inner = """
        SELECT id,
          ROW_NUMBER() OVER (
            PARTITION BY
              user_id,
              ((occurred_at AT TIME ZONE %s)::date),
              LOWER(TRIM(description)),
              amount_cents
            ORDER BY id ASC
          ) AS rn
        FROM transactions
    """
    params: list[object] = [tz]
    if user_id is not None:
        inner += " WHERE user_id = %s"
        params.append(user_id)

    sql = f"""
    DELETE FROM transactions
    WHERE id IN (
      SELECT id FROM (
        {inner}
      ) sub WHERE rn > 1
    )
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def delete_same_day_same_description_keep_newest(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
) -> int:
    """
    Same user + same **local** calendar day in ``tz_name`` + same description (trimmed, case-insensitive),
    any amount. Keeps the row with latest occurred_at, then highest id; deletes the rest.
    """
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    inner = """
        SELECT id,
          ROW_NUMBER() OVER (
            PARTITION BY
              user_id,
              ((occurred_at AT TIME ZONE %s)::date),
              LOWER(TRIM(description))
            ORDER BY occurred_at DESC, id DESC
          ) AS rn
        FROM transactions
    """
    params: list[object] = [tz]
    if user_id is not None:
        inner += " WHERE user_id = %s"
        params.append(user_id)

    sql = f"""
    DELETE FROM transactions
    WHERE id IN (
      SELECT id FROM (
        {inner}
      ) sub WHERE rn > 1
    )
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def delete_nighttime_transactions(
    *,
    tz_name: str,
    user_id: int | None = None,
    exclude_descriptions: frozenset[str] | None = None,
) -> int:
    """
    Delete rows whose local wall-clock hour in ``tz_name`` is 21–23 or 0–6.
    Skips Paycheck/Rent by default so recurring seeds are not removed.
    """
    from .db import connect

    exclude = exclude_descriptions or frozenset(
        {
            "paycheck",
            "rent",
            "subscription",
            "cloud storage",
            "streaming",
        }
    )
    placeholders = ", ".join(["%s"] * len(exclude))

    inner = f"""
        SELECT t.id FROM transactions t
        WHERE (
          EXTRACT(HOUR FROM (t.occurred_at AT TIME ZONE %s))::int >= 21
          OR EXTRACT(HOUR FROM (t.occurred_at AT TIME ZONE %s))::int < 7
        )
        AND LOWER(TRIM(t.description)) NOT IN ({placeholders})
    """
    params: list[object] = [tz_name, tz_name, *exclude]
    if user_id is not None:
        inner += " AND t.user_id = %s"
        params.append(user_id)

    sql = f"DELETE FROM transactions WHERE id IN ({inner})"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def normalize_brunch_transactions(user_id: int | None = None) -> int:
    """
    Rows titled ``Brunch Saturday`` (trimmed, case-insensitive) → description ``Brunch`` and
    occurred_at in local 10:30–15:00 same calendar day (DEMO_SEED_TIMEZONE). Time from Random(id).
    """
    import random

    from datetime import timezone as dt_utc

    from .db import connect
    from .seed_random_times import random_brunch_time, seed_timezone

    tz = seed_timezone()
    where = "LOWER(TRIM(description)) = 'brunch saturday'"
    params: list[object] = []
    if user_id is not None:
        where += " AND user_id = %s"
        params.append(user_id)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, occurred_at FROM transactions WHERE {where}",
                params,
            )
            rows = cur.fetchall()
            n = 0
            for row_id, occurred_at in rows:
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=dt_utc.utc)
                local = occurred_at.astimezone(tz)
                d = local.date()
                rng = random.Random(int(row_id))
                new_utc = random_brunch_time(rng, d.year, d.month, d.day)
                cur.execute(
                    """
                    UPDATE transactions
                    SET description = %s, occurred_at = %s
                    WHERE id = %s
                    """,
                    ("Brunch", new_utc, row_id),
                )
                n += cur.rowcount
        conn.commit()
    return int(n)


def cap_gas_transactions_per_utc_month(
    user_id: int | None = None,
    *,
    keep: int = 2,
    tz_name: str | None = None,
) -> int:
    """
    Per user and **insights-local calendar month**, keep the ``keep`` newest Gas rows
    (by occurred_at, then id); delete the rest (description ``gas``, case-insensitive).
    """
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    inner = """
        SELECT id,
          ROW_NUMBER() OVER (
            PARTITION BY user_id, date_trunc('month', occurred_at AT TIME ZONE %s)
            ORDER BY occurred_at DESC, id DESC
          ) AS rn
        FROM transactions
        WHERE LOWER(TRIM(description)) = 'gas'
    """
    params: list[object] = [tz]
    if user_id is not None:
        inner += " AND user_id = %s"
        params.append(user_id)

    sql = f"""
    DELETE FROM transactions
    WHERE id IN (
      SELECT id FROM (
        {inner}
      ) sub WHERE rn > %s
    )
    """
    params.append(keep)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def cap_monthly_subscription_like_rows(
    user_id: int | None = None,
    *,
    tz_name: str | None = None,
    keep: int = 1,
) -> int:
    """
    Per user, per **insights-local calendar month**, and per description
    (``cloud storage``, ``subscription``, ``streaming``), keep ``keep`` rows.
    Prefers local calendar day 1 in ``tz_name``, then earliest ``occurred_at``, then lowest ``id``.
    """
    from .db import connect

    tz = tz_name or resolve_insights_timezone_name()

    inner = """
        SELECT id,
          ROW_NUMBER() OVER (
            PARTITION BY
              user_id,
              date_trunc('month', occurred_at AT TIME ZONE %s),
              LOWER(TRIM(description))
            ORDER BY
              CASE
                WHEN EXTRACT(
                  DAY FROM (occurred_at AT TIME ZONE %s)
                )::int = 1 THEN 0
                ELSE 1
              END,
              occurred_at ASC,
              id ASC
          ) AS rn
        FROM transactions
        WHERE LOWER(TRIM(description)) IN ('cloud storage', 'subscription', 'streaming')
    """
    params: list[object] = [tz, tz]
    if user_id is not None:
        inner += " AND user_id = %s"
        params.append(user_id)

    sql = f"""
    DELETE FROM transactions
    WHERE id IN (
      SELECT id FROM (
        {inner}
      ) sub WHERE rn > %s
    )
    """
    params.append(keep)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def delete_whole_foods_run_violating_min_local_gap(
    user_id: int | None = None,
    *,
    min_gap_days: int = 3,
    tz_name: str | None = None,
) -> int:
    """
    For ``Whole Foods run`` rows, sort by ``occurred_at`` and keep a row if its local date
    (``tz_name``) is at least ``min_gap_days`` after the last kept row's local date; delete others.
    """
    from collections import defaultdict
    from datetime import date, timezone as dt_utc

    from zoneinfo import ZoneInfo

    from .db import connect

    tz = ZoneInfo(tz_name or resolve_insights_timezone_name())
    where = "LOWER(TRIM(description)) = 'whole foods run'"
    params: list[object] = []
    if user_id is not None:
        where += " AND user_id = %s"
        params.append(user_id)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT user_id, id, occurred_at FROM transactions WHERE {where} "
                "ORDER BY user_id, occurred_at ASC, id ASC",
                params,
            )
            rows = cur.fetchall()

    by_user: dict[int, list[tuple[int, object]]] = defaultdict(list)
    for uid, tid, at in rows:
        by_user[uid].append((tid, at))

    to_delete: list[int] = []
    for uid, lst in by_user.items():
        last_kept: date | None = None
        for tid, at in lst:
            if at.tzinfo is None:
                at = at.replace(tzinfo=dt_utc.utc)
            ld = at.astimezone(tz).date()
            if last_kept is None or (ld - last_kept).days >= min_gap_days:
                last_kept = ld
            else:
                to_delete.append(tid)

    if not to_delete:
        return 0

    placeholders = ",".join(["%s"] * len(to_delete))
    sql = f"DELETE FROM transactions WHERE id IN ({placeholders})"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, to_delete)
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)
