from .category_store import ensure_categories_table
from .transaction_store import ensure_transactions_table
from .user_store import ensure_users_table


def ensure_schema() -> None:
    """
    Ensure DB schema exists once at app startup.
    """

    ensure_users_table()
    ensure_categories_table()
    ensure_transactions_table()
