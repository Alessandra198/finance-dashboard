# Personal Finance Dashboard (Resume Project)

Full-stack personal finance demo:

- **Backend:** Python, FastAPI, PostgreSQL, cookie sessions, PBKDF2 password hashes
- **Frontend:** HTML, CSS, JavaScript (vanilla SPA) in `frontend/`

Implemented: **auth** (register/login), **transactions** CRUD, **categories**, **insights** (summary with monthly series and category breakdown), **view-only users** (`read_only` flag; default viewer **`viewers@example.com`** — see `backend/.env.example`).

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SESSION_SECRET="dev-secret-change-me"
export DATABASE_URL="postgresql://finance:finance@127.0.0.1:5432/finance"
uvicorn app.main:app --reload --reload-dir app --port 8000
```

Use `--reload-dir app` so only the `app/` package is watched; changes under `scripts/` do not restart the server.

`SESSION_SECRET` is required when the API **issues or validates sessions** (login, authenticated routes). Scripts that only import helpers such as `hash_password` can run without it.

Portfolio **view-only** demo login (after seeding): **`viewers@example.com`** / **`Viewer1!`** — see **`backend/.env.example`**. Copy to **`backend/.env`**, set **`DEMO_PRIMARY_EMAIL`** and **`DEMO_SEED_PASSWORD`** too, then run the seed script ([backend/README.md](backend/README.md)). Do not commit `.env`.

### Frontend

Serve the static `frontend/` directory with any static file server (for example `python3 -m http.server 3000` from `frontend/`). Default API CORS allows `http://localhost:3000` and `http://127.0.0.1:3000`.

### Database

Ensure Postgres is reachable, then set `DATABASE_URL` as above. Demo seeds and repair scripts live under `backend/scripts/`; see [backend/README.md](backend/README.md) for insights timezone and cleanup commands.

## Insights timezone

Monthly buckets and demo repair/dedupe use **`INSIGHTS_TIMEZONE` → `DEMO_SEED_TIMEZONE` → `Europe/Rome`** (see `app/insights_timezone.py`). Set `INSIGHTS_TIMEZONE=UTC` for strict UTC months everywhere.
