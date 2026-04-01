"""
Repair Paycheck/Rent rows: correct dates, remove duplicate rows in the same **insights-local** month
(see ``resolve_insights_timezone_name()``), and (for a single user or the configured primary demo user)
normalize amounts.

By default: fixes **all users** for dates + deduplication, then normalizes amounts only for the user
whose email matches ``DEMO_PRIMARY_EMAIL`` (if that env var is set and the user exists).

Run from backend/: PYTHONPATH=. python3 scripts/realign_paychecks_to_month_end.py

Optional: DEMO_REALIGN_EMAIL=you@example.com — limit realign/dedupe/normalize to that user only.
"""

import os

from app.demo_identity import demo_primary_email
from app.demo_paycheck_schedule import normalize_demo_recurring_amounts, repair_recurring_demo_data
from app.user_store import ensure_users_table, get_user_by_email


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set")
    ensure_users_table()
    email = os.getenv("DEMO_REALIGN_EMAIL", "").strip()
    if email:
        user = get_user_by_email(email)
        if user is None:
            raise SystemExit(f"No user {email!r}")
        fix = repair_recurring_demo_data(user.id)
        print(f"Repair for {email} (user_id={user.id}):")
    else:
        fix = repair_recurring_demo_data(None)
        print("Repair for all users (dates + dedupe; amounts not changed globally):")
        primary = demo_primary_email()
        demo = get_user_by_email(primary) if primary else None
        if demo:
            np, nr = normalize_demo_recurring_amounts(demo.id)
            fix = {**fix, "paychecks_amount_normalized": fix["paychecks_amount_normalized"] + np}
            fix["rent_amount_normalized"] = fix["rent_amount_normalized"] + nr
            print(f"Also normalized amounts for configured primary demo user: +{np} pay rows, +{nr} rent rows.")
    for k, v in fix.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
