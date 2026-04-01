import os
import secrets
from datetime import datetime, timezone

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.security import hash_password
from app.user_store import create_user


def _cleanup_user_by_email(email: str) -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))


def test_auth_register_login_me_and_insights() -> None:
    if not os.getenv("DATABASE_URL"):
        raise AssertionError("DATABASE_URL must be set to run tests")

    email = f"test_{secrets.token_hex(6)}@example.com"
    password = "TestPass!2345"

    _cleanup_user_by_email(email)

    client = TestClient(app)

    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text

    r = client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["email"] == email

    # Create a category
    r = client.post("/api/categories", json={"name": "Groceries"})
    assert r.status_code == 200, r.text

    # Create a couple transactions (expense + income)
    occurred_at = datetime.now(timezone.utc).isoformat()
    r = client.post(
        "/api/transactions",
        json={"amount_cents": -1299, "occurred_at": occurred_at, "description": "Groceries"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/transactions",
        json={"amount_cents": 250000, "occurred_at": occurred_at, "description": "Paycheck"},
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/insights/summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "income_cents" in data
    assert "expense_cents" in data
    assert "net_cents" in data
    assert isinstance(data["monthly"], list)
    assert isinstance(data["expense_by_category"], list)

    _cleanup_user_by_email(email)


def test_read_only_account_blocks_mutations() -> None:
    if not os.getenv("DATABASE_URL"):
        raise AssertionError("DATABASE_URL must be set to run tests")

    email = f"ro_{secrets.token_hex(6)}@example.com"
    password = "TestPass!2345"
    _cleanup_user_by_email(email)

    create_user(email, hash_password(password), read_only=True)

    client = TestClient(app)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text

    r = client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    assert r.json().get("read_only") is True

    occurred_at = datetime.now(timezone.utc).isoformat()
    r = client.get("/api/transactions")
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/transactions",
        json={"amount_cents": -200, "occurred_at": occurred_at, "description": "blocked"},
    )
    assert r.status_code == 403, r.text

    r = client.post("/api/categories", json={"name": "Nope"})
    assert r.status_code == 403, r.text

    _cleanup_user_by_email(email)

