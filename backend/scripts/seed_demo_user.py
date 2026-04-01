import os
import random
from datetime import datetime, timedelta, timezone

from app.category_store import create_category, ensure_categories_table, list_categories
from app.seed_random_times import random_occurred_at, seed_timezone
from app.demo_paycheck_schedule import (
    DEMO_PAYCHECK_CENTS,
    DEMO_RENT_CENTS,
    monthly_recurring_exists,
    paycheck_at_month,
    repair_recurring_demo_data,
)
from app.db import connect
from app.demo_identity import (
    require_demo_primary_email,
    require_demo_seed_password,
    require_demo_viewer_email,
    require_demo_viewer_password,
)
from app.security import hash_password
from app.transaction_store import create_transaction, ensure_transactions_table
from app.user_store import (
    create_user,
    ensure_users_table,
    get_user_by_email,
    get_user_by_id,
    set_user_read_only,
)

PAYCHECK_CENTS = DEMO_PAYCHECK_CENTS
RENT_CENTS = DEMO_RENT_CENTS
RENT_DAY = 1
RENT_HOUR = 10
RENT_MINUTE = 0


def copy_user_finance_data(src_user_id: int, dst_user_id: int) -> None:
    """Replace dst user's categories and transactions with a copy of src (timestamps preserved)."""
    ensure_categories_table()
    ensure_transactions_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM transactions WHERE user_id = %s", (dst_user_id,))
            cur.execute("DELETE FROM categories WHERE user_id = %s", (dst_user_id,))

            cur.execute(
                "SELECT id, name, created_at FROM categories WHERE user_id = %s ORDER BY id ASC",
                (src_user_id,),
            )
            cat_rows = cur.fetchall()
            id_map: dict[int, int] = {}
            for old_id, name, cat_created in cat_rows:
                cur.execute(
                    "INSERT INTO categories (user_id, name, created_at) VALUES (%s, %s, %s) RETURNING id",
                    (dst_user_id, name, cat_created),
                )
                row = cur.fetchone()
                if row:
                    id_map[int(old_id)] = int(row[0])

            cur.execute(
                """
                SELECT category_id, amount_cents, description, occurred_at, created_at
                FROM transactions
                WHERE user_id = %s
                ORDER BY id ASC
                """,
                (src_user_id,),
            )
            for cat_id, amt, desc, occ, cre in cur.fetchall():
                if cat_id is None:
                    new_cat = None
                else:
                    new_cat = id_map.get(int(cat_id))

                cur.execute(
                    """
                    INSERT INTO transactions (user_id, category_id, amount_cents, description, occurred_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (dst_user_id, new_cat, amt, desc, occ, cre),
                )


def _iter_year_months_inclusive(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """All (year, month) pairs from start's month through end's month."""
    y, m = start.year, start.month
    end_y, end_m = end.year, end.month
    out: list[tuple[int, int]] = []
    while (y, m) <= (end_y, end_m):
        out.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


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


def _create_recurring_if_absent(
    user_id: int,
    *,
    amount_cents: int,
    occurred_at: datetime,
    description: str,
    category_id: int | None,
) -> None:
    if monthly_recurring_exists(user_id, occurred_at=occurred_at, description=description):
        return
    create_transaction(
        user_id,
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        description=description,
        category_id=category_id,
    )


def seed_demo_user_account(email: str, password: str, *, read_only: bool = False) -> None:
    ensure_users_table()
    user = get_user_by_email(email)
    if user is None:
        user = create_user(email, hash_password(password), read_only=read_only)
    elif user.read_only != read_only:
        set_user_read_only(user.id, read_only)
        user = get_user_by_id(user.id)
        assert user is not None

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
        "Health",
        "Entertainment",
    ]

    existing = {c.name: c for c in list_categories(user.id)}
    category_ids = {}
    for name in base_categories:
        if name in existing:
            category_ids[name] = existing[name].id
        else:
            category_ids[name] = create_category(user.id, name).id

    rng = random.Random()

    now = datetime.now(timezone.utc)
    days = 120
    cutoff = now - timedelta(days=days)

    # One paycheck and one rent per month — only when that instant falls in the seed window.
    for year, month in _iter_year_months_inclusive(cutoff, now):
        p_at = paycheck_at_month(year, month)
        if cutoff <= p_at <= now:
            _create_recurring_if_absent(
                user.id,
                amount_cents=PAYCHECK_CENTS,
                occurred_at=p_at,
                description="Paycheck",
                category_id=None,
            )
        rent_at = datetime(year, month, RENT_DAY, RENT_HOUR, RENT_MINUTE, tzinfo=timezone.utc)
        if cutoff <= rent_at <= now:
            _create_recurring_if_absent(
                user.id,
                amount_cents=RENT_CENTS,
                occurred_at=rent_at,
                description="Rent",
                category_id=category_ids["Rent"],
            )

    # Random daily spend.
    spend_choices = [
        ("Groceries", -rng.randint(2500, 18000), "Groceries"),
        ("Restaurants", -rng.randint(1800, 9000), "Dinner"),
        ("Coffee", -rng.randint(350, 950), "Coffee"),
        ("Transport", -rng.randint(250, 2500), "Transport"),
        ("Utilities", -rng.randint(3000, 15000), "Utilities"),
        ("Subscriptions", -rng.randint(800, 3500), "Subscription"),
        ("Shopping", -rng.randint(1200, 22000), "Shopping"),
        ("Health", -rng.randint(800, 15000), "Health"),
        ("Entertainment", -rng.randint(700, 12000), "Entertainment"),
    ]

    tz = seed_timezone()
    for d in range(days):
        if rng.random() < 0.55:
            # 0-3 transactions/day; local wall time 07:00–20:59 only (see seed_random_times).
            local_date = (now.astimezone(tz) - timedelta(days=d)).date()
            for _ in range(rng.randint(0, 3)):
                cat, amt, desc = rng.choice(spend_choices)
                occurred_at = random_occurred_at(rng, local_date.year, local_date.month, local_date.day)
                _create_transaction_if_missing(
                    user.id,
                    amount_cents=int(amt),
                    occurred_at=occurred_at,
                    description=desc,
                    category_id=category_ids[cat],
                )

    fix = repair_recurring_demo_data(user.id)
    ro = " (view-only account)" if read_only else ""
    print(f"Seeded random data for primary demo user (user_id={user.id}){ro}.")
    print(
        "Recurring repair:",
        f"pay realigned {fix['paychecks_realigned']}, rent realigned {fix['rent_realigned']},",
        f"pay deduped {fix['paychecks_deduped']}, rent deduped {fix['rent_deduped']},",
        f"amounts pay {fix['paychecks_amount_normalized']}, rent {fix['rent_amount_normalized']},",
        f"same-day exact {fix['same_day_exact_duplicates_deleted']}, same-desc {fix['same_day_same_desc_deleted']},",
        f"night purge {fix['nighttime_local_deleted']}.",
    )


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set")

    primary_email = require_demo_primary_email()
    viewer_email = require_demo_viewer_email()
    viewer_password = require_demo_viewer_password()
    seed_password = require_demo_seed_password()

    seed_demo_user_account(primary_email, seed_password, read_only=False)

    ensure_users_table()
    demo_user = get_user_by_email(primary_email)
    if demo_user is None:
        raise SystemExit("Expected primary demo user after seed (check DEMO_PRIMARY_EMAIL).")

    viewer = get_user_by_email(viewer_email)
    if viewer is None:
        viewer = create_user(viewer_email, hash_password(viewer_password), read_only=True)
    else:
        if not viewer.read_only:
            set_user_read_only(viewer.id, True)
        refetched = get_user_by_id(viewer.id)
        if refetched is None:
            raise SystemExit("View-only user missing after fetch.")
        viewer = refetched

    copy_user_finance_data(demo_user.id, viewer.id)
    print(f"Mirrored categories and transactions to view-only user (user_id={viewer.id}).")


if __name__ == "__main__":
    main()

