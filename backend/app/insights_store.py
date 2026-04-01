from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import connect
from .insights_timezone import resolve_insights_timezone_name
from .transaction_store import ensure_transactions_table


@dataclass(frozen=True)
class InsightsSummary:
    from_date: date
    to_date: date
    income_cents: int
    expense_cents: int
    net_cents: int
    monthly: list[dict]
    expense_by_category: list[dict]


def _default_range() -> tuple[date, date]:
    # Default: last 12 months through today (inclusive end in API, exclusive in SQL).
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=365), today)


def get_summary(
    user_id: int,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    top_categories: int = 10,
) -> InsightsSummary:
    ensure_transactions_table()

    if from_date is None or to_date is None:
        d_from, d_to = _default_range()
        from_date = from_date or d_from
        to_date = to_date or d_to

    if from_date > to_date:
        raise ValueError("from must be <= to")

    # Half-open [from, to+1day) in local TZ; monthly buckets use the same name as repair/dedupe.
    tz_name = resolve_insights_timezone_name()
    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = timezone.utc
    start_local = datetime(from_date.year, from_date.month, from_date.day, tzinfo=local_tz)
    end_local = datetime(to_date.year, to_date.month, to_date.day, tzinfo=local_tz) + timedelta(days=1)
    start_dt = start_local.astimezone(timezone.utc)
    end_dt = end_local.astimezone(timezone.utc)

    with connect() as conn:
        with conn.cursor() as cur:
            # Totals: income is positive amounts, expense is absolute value of negative amounts.
            cur.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN amount_cents > 0 THEN amount_cents ELSE 0 END), 0) AS income_cents,
                  COALESCE(SUM(CASE WHEN amount_cents < 0 THEN -amount_cents ELSE 0 END), 0) AS expense_cents,
                  COALESCE(SUM(amount_cents), 0) AS net_cents
                FROM transactions
                WHERE user_id = %s
                  AND occurred_at >= %s
                  AND occurred_at < %s
                """,
                (user_id, start_dt, end_dt),
            )
            income_cents, expense_cents, net_cents = cur.fetchone() or (0, 0, 0)

            # Monthly series by *local* calendar month in tz_name (not DB session TZ).
            cur.execute(
                """
                SELECT
                  (date_trunc('month', occurred_at AT TIME ZONE %s))::date AS month,
                  COALESCE(SUM(CASE WHEN amount_cents > 0 THEN amount_cents ELSE 0 END), 0) AS income_cents,
                  COALESCE(SUM(CASE WHEN amount_cents < 0 THEN -amount_cents ELSE 0 END), 0) AS expense_cents,
                  COALESCE(SUM(amount_cents), 0) AS net_cents
                FROM transactions
                WHERE user_id = %s
                  AND occurred_at >= %s
                  AND occurred_at < %s
                GROUP BY 1
                ORDER BY 1
                """,
                (tz_name, user_id, start_dt, end_dt),
            )
            monthly_rows = cur.fetchall()
            monthly = []
            for r in monthly_rows:
                m = r[0]
                if hasattr(m, "date"):
                    m = m.date()
                monthly.append(
                    {
                        "month": m.isoformat(),
                        "income_cents": int(r[1]),
                        "expense_cents": int(r[2]),
                        "net_cents": int(r[3]),
                    }
                )

            # Expense by category (expenses only).
            cur.execute(
                """
                SELECT
                  COALESCE(c.name, 'Uncategorized') AS category,
                  COALESCE(SUM(-t.amount_cents), 0) AS expense_cents
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.user_id = %s
                  AND t.occurred_at >= %s
                  AND t.occurred_at < %s
                  AND t.amount_cents < 0
                GROUP BY 1
                ORDER BY expense_cents DESC
                LIMIT %s
                """,
                (user_id, start_dt, end_dt, top_categories),
            )
            cat_rows = cur.fetchall()
            expense_by_category = [{"category": str(r[0]), "expense_cents": int(r[1])} for r in cat_rows]

    return InsightsSummary(
        from_date=from_date,
        to_date=to_date,
        income_cents=int(income_cents),
        expense_cents=int(expense_cents),
        net_cents=int(net_cents),
        monthly=monthly,
        expense_by_category=expense_by_category,
    )

