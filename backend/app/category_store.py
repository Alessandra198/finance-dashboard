from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .db import connect
from .user_store import ensure_users_table


@dataclass(frozen=True)
class Category:
    id: int
    user_id: int
    name: str
    created_at: datetime


_CREATE_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS categories (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);
"""

_categories_table_ready = False
_categories_table_lock = Lock()


def ensure_categories_table() -> None:
    global _categories_table_ready
    if _categories_table_ready:
        return
    with _categories_table_lock:
        if _categories_table_ready:
            return
        ensure_users_table()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_CATEGORIES_TABLE_SQL)
        _categories_table_ready = True


def create_category(user_id: int, name: str) -> Category:
    ensure_categories_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO categories (user_id, name) VALUES (%s, %s) RETURNING id, created_at",
                (user_id, name),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to insert category")
            category_id, created_at = row
            return Category(
                id=int(category_id),
                user_id=int(user_id),
                name=str(name),
                created_at=created_at,
            )


def list_categories(user_id: int) -> list[Category]:
    ensure_categories_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, name, created_at FROM categories WHERE user_id = %s ORDER BY name ASC",
                (user_id,),
            )
            rows = cur.fetchall()
            return [
                Category(
                    id=int(r[0]),
                    user_id=int(r[1]),
                    name=str(r[2]),
                    created_at=r[3],
                )
                for r in rows
            ]


def get_category_by_id(user_id: int, category_id: int) -> Category | None:
    ensure_categories_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, name, created_at FROM categories WHERE id = %s AND user_id = %s",
                (category_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Category(
                id=int(row[0]),
                user_id=int(row[1]),
                name=str(row[2]),
                created_at=row[3],
            )

