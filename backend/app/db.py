import os

import psycopg


def get_database_url() -> str:
    """
    Later we will use this to connect to Postgres.

    For now, the scaffold keeps DB integration as a follow-up checklist item.
    """

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def connect() -> psycopg.Connection:
    """
    Create a Postgres connection using DATABASE_URL.

    We keep this small and synchronous for now (psycopg). Later we can add pooling.
    """

    return psycopg.connect(get_database_url())

