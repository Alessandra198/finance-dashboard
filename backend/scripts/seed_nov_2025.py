"""
Insert fake transactions for the primary demo user (``DEMO_PRIMARY_EMAIL``).
- October 2025 through March 2026 (default charts use Oct–Mar for six months of trends)
- Alternating months: heavier discretionary vs tighter spend + occasional freelance income so
  several months show positive net / savings rate in insights.
Run from backend/: set env from ``.env.example``, then ``PYTHONPATH=. python3 scripts/seed_nov_2025.py``.
"""

import calendar
import os
import random
from datetime import date, datetime, timedelta, timezone

from app.category_store import create_category, ensure_categories_table, list_categories
from app.demo_paycheck_schedule import (
    DEMO_PAYCHECK_CENTS,
    DEMO_RENT_CENTS,
    FEB_2026_DEMO_REWARDS_CENTS,
    monthly_recurring_exists,
    paycheck_at_month,
    repair_recurring_demo_data,
)
from app.db import connect
from app.demo_identity import require_demo_primary_email, require_demo_seed_password
from app.security import hash_password
from app.seed_random_times import random_brunch_time, random_occurred_at
from app.transaction_store import create_transaction, ensure_transactions_table
from app.user_store import create_user, ensure_users_table, get_user_by_email

# Recurring amounts: use demo_paycheck_schedule (single source of truth).
PAYCHECK_CENTS = DEMO_PAYCHECK_CENTS
RENT_CENTS = DEMO_RENT_CENTS

# Paycheck: last calendar day of each month. Rent: 1st of month. Times UTC.
RENT_DAY = 1
RENT_HOUR = 10
RENT_MINUTE = 0

# Fraction of random spend picks that use the Gas template (rest split across non-gas templates).
GAS_TEMPLATE_PROB = 0.06

# Monthly subs (same calendar day / time as rent — 1st, RENT_HOUR:RENT_MINUTE UTC).
SUBSCRIPTION_CENTS = -2644  # $26.44
CLOUD_STORAGE_CENTS = -999  # $9.99

# "Whole Foods run" is seeded separately with at least this many days between rows (not daily random).
WHOLE_FOODS_MIN_GAP_DAYS = 3
WHOLE_FOODS_DESC = "Whole Foods run"

# Lighter spend + one freelance inflow so the default 6‑month chart shows positive savings in ~half the months.
TIGHT_SAVINGS_MONTHS = frozenset({(2025, 10), (2025, 12), (2026, 2)})
FREELANCE_BONUS_CENTS = 100_000  # $1,000 extra income in “tight” months for visible positive savings rate
# February is only 28 days in 2026 but still carries full rent + utilities; add a second inflow so the
# savings-rate bar stays clearly positive even with unlucky RNG on discretionary lines.
FEB_WHOLE_FOODS_MAX_TRIPS = 3


def _pick_spend_template(
    rng: random.Random,
    spend_templates: list[tuple[str, str, int, int]],
) -> tuple[str, str, int, int]:
    non_gas = [t for t in spend_templates if t[1] != "Gas"]
    gas_tpl = next(t for t in spend_templates if t[1] == "Gas")
    if rng.random() < GAS_TEMPLATE_PROB:
        return gas_tpl
    return rng.choice(non_gas)


def _occurred_for_desc(
    rng: random.Random, year: int, month: int, day: int, desc: str
) -> datetime:
    if desc.strip().lower() == "brunch":
        return random_brunch_time(rng, year, month, day)
    return random_occurred_at(rng, year, month, day)


def _seed_daily_random_spending(
    user_id: int,
    year: int,
    month: int,
    rng: random.Random,
    spend_templates: list[tuple[str, str, int, int]],
    category_ids: dict[str, int],
    *,
    spendiness: str,
) -> None:
    if spendiness == "loose":
        day_prob, n_lo, n_hi = 0.52, 1, 3
    elif spendiness == "tight" and month == 2:
        day_prob, n_lo, n_hi = 0.12, 1, 1
    else:
        day_prob, n_lo, n_hi = 0.26, 1, 2
    last_day = calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        if rng.random() < day_prob:
            n = rng.randint(n_lo, n_hi)
            for _ in range(n):
                cat_name, desc, lo, hi = _pick_spend_template(rng, spend_templates)
                exp_min = min(abs(lo), abs(hi))
                exp_max = max(abs(lo), abs(hi))
                cents = -rng.randint(exp_min, exp_max)
                _create_transaction_if_missing(
                    user_id,
                    amount_cents=int(cents),
                    occurred_at=_occurred_for_desc(rng, year, month, day, desc),
                    description=desc,
                    category_id=category_ids[cat_name],
                )


def _dt(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _whole_foods_days_for_month(
    rng: random.Random,
    year: int,
    month: int,
    *,
    prev_last_local: date | None,
) -> list[int]:
    """
    Calendar days in ``month`` for Whole Foods, each at least ``WHOLE_FOODS_MIN_GAP_DAYS``
    after the previous row's local date (including ``prev_last_local`` from the prior month).
    """
    last_day = calendar.monthrange(year, month)[1]
    first_this = date(year, month, 1)
    last_this = date(year, month, last_day)

    if prev_last_local is not None:
        earliest = prev_last_local + timedelta(days=WHOLE_FOODS_MIN_GAP_DAYS)
        if earliest > last_this:
            return []
        if earliest >= first_this:
            start_d = earliest.day
        else:
            start_d = rng.randint(1, min(WHOLE_FOODS_MIN_GAP_DAYS + 1, last_day))
    else:
        start_d = rng.randint(1, min(WHOLE_FOODS_MIN_GAP_DAYS + 1, last_day))

    days: list[int] = []
    d = start_d
    while d <= last_day:
        days.append(d)
        d += WHOLE_FOODS_MIN_GAP_DAYS + rng.randint(0, 4)
    # Shorter February: fewer grocery runs so fixed costs don’t swamp the month in charts.
    if month == 2 and len(days) > FEB_WHOLE_FOODS_MAX_TRIPS:
        days = days[:FEB_WHOLE_FOODS_MAX_TRIPS]
    return days


def _seed_whole_foods_run_spaced(
    user_id: int,
    *,
    year: int,
    month: int,
    rng: random.Random,
    category_ids: dict[str, int],
    prev_last_local: date | None,
) -> date | None:
    days = _whole_foods_days_for_month(
        rng, year, month, prev_last_local=prev_last_local
    )
    last_wf = prev_last_local
    for day in days:
        cents = -rng.randint(8500, 15000)
        _create_transaction_if_missing(
            user_id,
            amount_cents=cents,
            occurred_at=random_occurred_at(rng, year, month, day),
            description=WHOLE_FOODS_DESC,
            category_id=category_ids["Groceries"],
        )
        last_wf = date(year, month, day)
    return last_wf


def _create_transaction_if_missing(
    user_id: int,
    *,
    amount_cents: int,
    occurred_at: datetime,
    description: str,
    category_id: int | None,
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM transactions
                WHERE user_id = %s
                  AND amount_cents = %s
                  AND description = %s
                  AND occurred_at = %s
                LIMIT 1
                """,
                (user_id, amount_cents, description, occurred_at),
            )
            if cur.fetchone() is not None:
                return
    create_transaction(
        user_id,
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        description=description,
        category_id=category_id,
    )


def _maybe_freelance_bonus(user_id: int, year: int, month: int) -> None:
    if (year, month) not in TIGHT_SAVINGS_MONTHS:
        return
    _create_transaction_if_missing(
        user_id,
        amount_cents=FREELANCE_BONUS_CENTS,
        occurred_at=_dt(year, month, 16, 11, 25),
        description="Freelance deposit",
        category_id=None,
    )


def _maybe_february_extra_income(user_id: int, year: int, month: int) -> None:
    if year != 2026 or month != 2:
        return
    _create_transaction_if_missing(
        user_id,
        amount_cents=FEB_2026_DEMO_REWARDS_CENTS,
        occurred_at=_dt(year, month, 24, 13, 10),
        description="Rewards payout (demo)",
        category_id=None,
    )


def _create_recurring_if_absent(
    user_id: int,
    *,
    amount_cents: int,
    occurred_at: datetime,
    description: str,
    category_id: int | None,
) -> None:
    """One Paycheck/Rent per user per UTC month (ignores amount — avoids duplicate seeds)."""
    if monthly_recurring_exists(user_id, occurred_at=occurred_at, description=description):
        return
    create_transaction(
        user_id,
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        description=description,
        category_id=category_id,
    )


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set")

    email = require_demo_primary_email()
    password = require_demo_seed_password()

    ensure_users_table()
    user = get_user_by_email(email)
    if user is None:
        user = create_user(email, hash_password(password))

    ensure_categories_table()
    ensure_transactions_table()

    base_categories = [
        "Rent",
        "Groceries",
        "Restaurants",
        "Coffee",
        "Transport",
        "Utilities",
        "Subscriptions",
        "Shopping",
    ]
    existing = {c.name: c for c in list_categories(user.id)}
    category_ids: dict[str, int] = {}
    for name in base_categories:
        if name in existing:
            category_ids[name] = existing[name].id
        else:
            category_ids[name] = create_category(user.id, name).id

    # October 2025: intentionally present but hidden by default chart range.
    rng_oct = random.Random(202510)
    _create_recurring_if_absent(
        user.id,
        amount_cents=PAYCHECK_CENTS,
        occurred_at=paycheck_at_month(2025, 10),
        description="Paycheck",
        category_id=None,
    )
    _create_recurring_if_absent(
        user.id,
        amount_cents=RENT_CENTS,
        occurred_at=_dt(2025, 10, RENT_DAY, RENT_HOUR, RENT_MINUTE),
        description="Rent",
        category_id=category_ids["Rent"],
    )
    _create_transaction_if_missing(
        user.id,
        amount_cents=-3_950,
        occurred_at=_dt(2025, 10, 4, 14, 22),
        description="Electric bill",
        category_id=category_ids["Utilities"],
    )
    _create_transaction_if_missing(
        user.id,
        amount_cents=-3_099,
        occurred_at=_dt(2025, 10, 20, 11, 45),
        description="Internet",
        category_id=category_ids["Utilities"],
    )

    # Varied daily-style spending (Whole Foods / Subscription / Cloud storage are scheduled separately).
    spend_templates = [
        ("Groceries", "Corner market", -1200, -4500),
        ("Restaurants", "Thai takeout", -2200, -6800),
        ("Restaurants", "Brunch", -3500, -12000),
        ("Coffee", "Coffee", -450, -950),
        ("Transport", "Gas", -3500, -7200),
        ("Transport", "Parking", -800, -2200),
        ("Shopping", "Bookstore", -1800, -5500),
    ]

    _create_recurring_if_absent(
        user.id,
        amount_cents=SUBSCRIPTION_CENTS,
        occurred_at=_dt(2025, 10, RENT_DAY, RENT_HOUR, RENT_MINUTE),
        description="Subscription",
        category_id=category_ids["Subscriptions"],
    )
    _create_recurring_if_absent(
        user.id,
        amount_cents=CLOUD_STORAGE_CENTS,
        occurred_at=_dt(2025, 10, RENT_DAY, RENT_HOUR, RENT_MINUTE),
        description="Cloud storage",
        category_id=category_ids["Subscriptions"],
    )
    _maybe_freelance_bonus(user.id, 2025, 10)

    last_wf_local: date | None = _seed_whole_foods_run_spaced(
        user.id,
        year=2025,
        month=10,
        rng=rng_oct,
        category_ids=category_ids,
        prev_last_local=None,
    )

    _seed_daily_random_spending(
        user.id,
        2025,
        10,
        rng_oct,
        spend_templates,
        category_ids,
        spendiness="tight",
    )

    # Nov 2025 through Mar 2026 (paycheck + rent same amounts as constants above).
    # "loose" = heavier discretionary (often negative savings rate); "tight" + freelance = clearer saving months.
    seeded_months = [
        (2025, 11, 202511, "loose"),
        (2025, 12, 202512, "tight"),
        (2026, 1, 202601, "loose"),
        (2026, 2, 202602, "tight"),
        (2026, 3, 202603, "loose"),
    ]
    for year, month, seed, spendiness in seeded_months:
        rng = random.Random(seed)
        _create_recurring_if_absent(
            user.id,
            amount_cents=PAYCHECK_CENTS,
            occurred_at=paycheck_at_month(year, month),
            description="Paycheck",
            category_id=None,
        )
        _create_recurring_if_absent(
            user.id,
            amount_cents=RENT_CENTS,
            occurred_at=_dt(year, month, RENT_DAY, RENT_HOUR, RENT_MINUTE),
            description="Rent",
            category_id=category_ids["Rent"],
        )
        _create_recurring_if_absent(
            user.id,
            amount_cents=SUBSCRIPTION_CENTS,
            occurred_at=_dt(year, month, RENT_DAY, RENT_HOUR, RENT_MINUTE),
            description="Subscription",
            category_id=category_ids["Subscriptions"],
        )
        _create_recurring_if_absent(
            user.id,
            amount_cents=CLOUD_STORAGE_CENTS,
            occurred_at=_dt(year, month, RENT_DAY, RENT_HOUR, RENT_MINUTE),
            description="Cloud storage",
            category_id=category_ids["Subscriptions"],
        )
        _create_transaction_if_missing(
            user.id,
            amount_cents=-4_200,
            occurred_at=_dt(year, month, 3, 14, 22),
            description="Electric bill",
            category_id=category_ids["Utilities"],
        )
        _create_transaction_if_missing(
            user.id,
            amount_cents=-3_199,
            occurred_at=_dt(year, month, 18, 11, 45),
            description="Internet",
            category_id=category_ids["Utilities"],
        )
        _maybe_freelance_bonus(user.id, year, month)
        _maybe_february_extra_income(user.id, year, month)

        last_wf_local = _seed_whole_foods_run_spaced(
            user.id,
            year=year,
            month=month,
            rng=rng,
            category_ids=category_ids,
            prev_last_local=last_wf_local,
        )

        _seed_daily_random_spending(
            user.id,
            year,
            month,
            rng,
            spend_templates,
            category_ids,
            spendiness=spendiness,
        )

    fix = repair_recurring_demo_data(user.id)
    print(f"Inserted Oct 2025 + Nov 2025 to Mar 2026 demo data for primary user (user_id={user.id}).")
    print(
        "Recurring repair:",
        f"paychecks realigned {fix['paychecks_realigned']}, rent realigned {fix['rent_realigned']},",
        f"pay deduped {fix['paychecks_deduped']}, rent deduped {fix['rent_deduped']},",
        f"amounts norm pay {fix['paychecks_amount_normalized']}, rent {fix['rent_amount_normalized']},",
        f"same-day exact {fix['same_day_exact_duplicates_deleted']}, same-desc {fix['same_day_same_desc_deleted']},",
        f"night purge {fix['nighttime_local_deleted']}, brunch norm {fix['brunch_normalized']},",
        f"subs cap {fix['subscription_like_capped_per_utc_month']}, wf gap {fix['whole_foods_min_gap_deleted']},",
        f"gas cap {fix['gas_capped_per_utc_month']}, feb rewards repair {fix['february_demo_rewards_inserted']}.",
    )


if __name__ == "__main__":
    main()
