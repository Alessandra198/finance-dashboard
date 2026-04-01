# Backend

FastAPI service for the finance dashboard.

## Run

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
export SESSION_SECRET="dev-secret-change-me"
export DATABASE_URL="postgresql://finance:finance@127.0.0.1:5432/finance"
uvicorn app.main:app --reload --reload-dir app --port 8000
```

`--reload-dir app` restricts the file watcher to the `app/` package so seed scripts and other files under `backend/` do not trigger reloads.

**Demo identities are env-only:** there are **no** demo email addresses in the codebase. Copy **`backend/.env.example`** → **`backend/.env`**, fill in **`DEMO_PRIMARY_EMAIL`**, **`DEMO_VIEWER_EMAIL`**, **`DEMO_VIEWER_PASSWORD`**, and **`DEMO_SEED_PASSWORD`**, then run seeds. Keep **`.env` gitignored** (see repo root `.gitignore`).

**View-only users:** accounts with **`read_only = true`** cannot mutate data; **`GET /api/auth/me`** includes **`read_only`**. **`scripts/seed_demo_user.py`** creates the primary user and a viewer user using those env vars and **mirrors** the primary user’s categories and transactions to the viewer.

If you rename the primary address in env, **update the `users.email` row** in Postgres to match (or start from a fresh DB) before re-seeding.

After **`backend/.env`** is filled, from **`backend/`**:

```bash
set -a && source .env && set +a
PYTHONPATH=. python3 scripts/seed_demo_user.py
```

Insights, repair, and dedupe scripts share **`resolve_insights_timezone_name()`**: **`INSIGHTS_TIMEZONE`**, then **`DEMO_SEED_TIMEZONE`**, then **`Europe/Rome`**. Same zone is used for monthly buckets, “same calendar day” dedupe, gas/subscription caps, and paycheck/rent realignment. Set **`INSIGHTS_TIMEZONE=UTC`** for strict UTC everywhere.

If **Paycheck** / **Rent** look wrong (wrong day, duplicates in one month, mixed amounts), run:

`PYTHONPATH=. python3 scripts/realign_paychecks_to_month_end.py`

This realigns dates, **dedupes to one row per user per insights-local month**, and normalizes amounts for the user named by **`DEMO_PRIMARY_EMAIL`** (if set) when fixing all users. **Without** `DEMO_REALIGN_EMAIL`, repair runs for **all users** (use with care on shared databases). To scope to one account:  
`DEMO_REALIGN_EMAIL=you@example.com PYTHONPATH=. python3 scripts/realign_paychecks_to_month_end.py`

(Seed scripts run the same repair for the seeded user after inserting data.)

**Cleanup** (`Brunch Saturday` → `Brunch` and local **10:30–15:00**; exact same-day dupes by **insights-local** day; same-day same description keeping newest; **Cloud storage** / **Subscription** / **Streaming** → 1 per **insights-local** month (prefer local day 1); **Whole Foods run** trimmed to ≥3 local days apart; local night 21:00–06:59 (skips Paycheck/Rent and those subs); cap **Gas** to 2 per user per **insights-local** month):

`PYTHONPATH=. python3 scripts/dedupe_same_day_transactions.py`

Optional: `DEDUPE_EMAIL=you@example.com`. Prefer **`INSIGHTS_TIMEZONE`** (or **`DEMO_SEED_TIMEZONE`**) to align with your data.

Random seed spending uses **07:00–20:59** in that timezone except **Brunch** (**10:30–15:00**). Whole Foods is spaced ≥3 local days apart across months (`scripts/seed_nov_2025.py`). Repair/dedupe enforces caps on legacy rows.

## Status

## Tests (smoke)

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
export SESSION_SECRET="test-secret"
export DATABASE_URL="postgresql://finance:finance@127.0.0.1:5432/finance"
pytest
```

