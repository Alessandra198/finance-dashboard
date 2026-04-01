from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .category_store import ensure_categories_table
from .db import connect
from .user_store import ensure_users_table


@dataclass(frozen=True)
class Transaction:
    id: int
    user_id: int
    category_id: int | None
    amount_cents: int
    description: str
    occurred_at: datetime
    created_at: datetime


_CREATE_TRANSACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INTEGER NULL REFERENCES categories(id) ON DELETE SET NULL,
  amount_cents INTEGER NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  occurred_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (amount_cents <> 0)
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_occurred_at
  ON transactions(user_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_category
  ON transactions(user_id, category_id);
"""

_transactions_table_ready = False
_transactions_table_lock = Lock()


def ensure_transactions_table() -> None:
    global _transactions_table_ready
    if _transactions_table_ready:
        return
    with _transactions_table_lock:
        if _transactions_table_ready:
            return
        ensure_users_table()
        ensure_categories_table()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TRANSACTIONS_TABLE_SQL)
        _transactions_table_ready = True


def _category_belongs_to_user(user_id: int, category_id: int) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM categories WHERE id = %s AND user_id = %s",
                (category_id, user_id),
            )
            return cur.fetchone() is not None


def create_transaction(
    user_id: int,
    *,
    amount_cents: int,
    occurred_at: datetime,
    description: str = "",
    category_id: int | None = None,
) -> Transaction:
    ensure_transactions_table()

    if category_id is not None and not _category_belongs_to_user(user_id, category_id):
        raise ValueError("Category does not exist")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (user_id, category_id, amount_cents, description, occurred_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (user_id, category_id, amount_cents, description, occurred_at),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to insert transaction")
            transaction_id, created_at = row
            return Transaction(
                id=int(transaction_id),
                user_id=int(user_id),
                category_id=int(category_id) if category_id is not None else None,
                amount_cents=int(amount_cents),
                description=str(description),
                occurred_at=occurred_at,
                created_at=created_at,
            )


def list_transactions(user_id: int, *, limit: int = 100, offset: int = 0) -> list[Transaction]:
    ensure_transactions_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, category_id, amount_cents, description, occurred_at, created_at
                FROM transactions
                WHERE user_id = %s
                ORDER BY occurred_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()
            return [
                Transaction(
                    id=int(r[0]),
                    user_id=int(r[1]),
                    category_id=int(r[2]) if r[2] is not None else None,
                    amount_cents=int(r[3]),
                    description=str(r[4]),
                    occurred_at=r[5],
                    created_at=r[6],
                )
                for r in rows
            ]


def update_transaction(
    user_id: int,
    transaction_id: int,
    *,
    amount_cents: int | None = None,
    occurred_at: datetime | None = None,
    description: str | None = None,
    category_id: int | None = None,
    clear_category: bool = False,
) -> Transaction | None:
    ensure_transactions_table()

    if category_id is not None and not _category_belongs_to_user(user_id, category_id):
        raise ValueError("Category does not exist")

    sets: list[str] = []
    params: list[object] = []

    if amount_cents is not None:
        sets.append("amount_cents = %s")
        params.append(amount_cents)
    if occurred_at is not None:
        sets.append("occurred_at = %s")
        params.append(occurred_at)
    if description is not None:
        sets.append("description = %s")
        params.append(description)
    if category_id is not None:
        sets.append("category_id = %s")
        params.append(category_id)
    elif clear_category:
        sets.append("category_id = %s")
        params.append(None)

    if not sets:
        # Nothing to update; return current record if it exists.
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, category_id, amount_cents, description, occurred_at, created_at
                    FROM transactions
                    WHERE id = %s AND user_id = %s
                    """,
                    (transaction_id, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return Transaction(
                    id=int(row[0]),
                    user_id=int(row[1]),
                    category_id=int(row[2]) if row[2] is not None else None,
                    amount_cents=int(row[3]),
                    description=str(row[4]),
                    occurred_at=row[5],
                    created_at=row[6],
                )

    params.extend([transaction_id, user_id])

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE transactions
                SET {", ".join(sets)}
                WHERE id = %s AND user_id = %s
                RETURNING id, user_id, category_id, amount_cents, description, occurred_at, created_at
                """,
                tuple(params),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Transaction(
                id=int(row[0]),
                user_id=int(row[1]),
                category_id=int(row[2]) if row[2] is not None else None,
                amount_cents=int(row[3]),
                description=str(row[4]),
                occurred_at=row[5],
                created_at=row[6],
            )


def delete_transaction(user_id: int, transaction_id: int) -> bool:
    ensure_transactions_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM transactions WHERE id = %s AND user_id = %s",
                (transaction_id, user_id),
            )
            return cur.rowcount == 1

