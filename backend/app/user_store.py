from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .db import connect


@dataclass(frozen=True)
class User:
    id: int
    email: str
    created_at: datetime
    password_hash: str
    read_only: bool = False


_CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  read_only BOOLEAN NOT NULL DEFAULT FALSE
);
"""

_ALTER_USERS_READ_ONLY_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS read_only BOOLEAN NOT NULL DEFAULT FALSE;
"""

_users_table_ready = False
_users_table_lock = Lock()


def ensure_users_table() -> None:
    global _users_table_ready
    if _users_table_ready:
        return
    with _users_table_lock:
        if _users_table_ready:
            return
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_USERS_TABLE_SQL)
                cur.execute(_ALTER_USERS_READ_ONLY_SQL)
        _users_table_ready = True


def create_user(email: str, password_hash: str, *, read_only: bool = False) -> User:
    ensure_users_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, read_only)
                VALUES (%s, %s, %s)
                RETURNING id, created_at
                """,
                (email, password_hash, read_only),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to insert user")

            user_id, created_at_db = row
            return User(
                id=int(user_id),
                email=email,
                created_at=created_at_db,
                password_hash=password_hash,
                read_only=read_only,
            )


def get_user_by_email(email: str) -> User | None:
    ensure_users_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at, password_hash, read_only FROM users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            user_id, email_db, created_at_db, password_hash_db, ro = row
            return User(
                id=int(user_id),
                email=str(email_db),
                created_at=created_at_db,
                password_hash=str(password_hash_db),
                read_only=bool(ro),
            )


def set_user_read_only(user_id: int, read_only: bool) -> None:
    ensure_users_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET read_only = %s WHERE id = %s", (read_only, user_id))


def get_user_by_id(user_id: int) -> User | None:
    ensure_users_table()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at, password_hash, read_only FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            uid, email_db, created_at_db, password_hash_db, ro = row
            return User(
                id=int(uid),
                email=str(email_db),
                created_at=created_at_db,
                password_hash=str(password_hash_db),
                read_only=bool(ro),
            )
