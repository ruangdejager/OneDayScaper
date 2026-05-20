import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)


_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        username    TEXT,
        keyword     TEXT NOT NULL COLLATE NOCASE,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, keyword)
    )
"""


@contextmanager
def _get_conn(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Always ensure table exists — idempotent and fast
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    # Warm up the connection — table creation now handled in _get_conn
    with _get_conn(db_path) as _:
        pass
    logger.info("Database ready at %s", db_path)


def add_subscription(db_path: str, user_id: int, username: str, keyword: str) -> bool:
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, username, keyword) VALUES (?, ?, ?)",
            (user_id, username, keyword.lower()),
        )
        return cursor.rowcount > 0


def remove_subscription(db_path: str, user_id: int, keyword: str) -> bool:
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM subscriptions WHERE user_id = ? AND keyword = ?",
            (user_id, keyword.lower()),
        )
        return cursor.rowcount > 0


def get_user_keywords(db_path: str, user_id: int) -> list[str]:
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT keyword FROM subscriptions WHERE user_id = ? ORDER BY keyword",
            (user_id,),
        ).fetchall()
        return [row["keyword"] for row in rows]


def get_all_subscriptions(db_path: str) -> dict[int, dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, username, keyword FROM subscriptions ORDER BY user_id"
        ).fetchall()

    result: dict[int, dict] = {}
    for row in rows:
        uid = row["user_id"]
        if uid not in result:
            result[uid] = {"username": row["username"], "keywords": []}
        result[uid]["keywords"].append(row["keyword"])
    return result
