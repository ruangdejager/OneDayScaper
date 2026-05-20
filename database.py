import logging
import os
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)


_CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        username    TEXT,
        keyword     TEXT NOT NULL COLLATE NOCASE,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, keyword)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sites (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        url         TEXT NOT NULL,
        name        TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, url)
    )
    """,
]


@contextmanager
def _get_conn(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Always ensure all tables exist — idempotent and fast
    for sql in _CREATE_TABLES:
        conn.execute(sql)
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
    abs_path = os.path.abspath(db_path)
    logger.info("add_subscription: file=%s user_id=%s keyword=%s", abs_path, user_id, keyword)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, username, keyword) VALUES (?, ?, ?)",
            (user_id, username, keyword.lower()),
        )
        inserted = cursor.rowcount > 0
        logger.info("add_subscription: inserted=%s", inserted)
        return inserted


def remove_subscription(db_path: str, user_id: int, keyword: str) -> bool:
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM subscriptions WHERE user_id = ? AND keyword = ?",
            (user_id, keyword.lower()),
        )
        return cursor.rowcount > 0


def get_user_keywords(db_path: str, user_id: int) -> list[str]:
    abs_path = os.path.abspath(db_path)
    logger.info("get_user_keywords: file=%s user_id=%s", abs_path, user_id)
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT keyword FROM subscriptions WHERE user_id = ? ORDER BY keyword",
            (user_id,),
        ).fetchall()
        keywords = [row["keyword"] for row in rows]
        logger.info("get_user_keywords: found=%s", keywords)
        return keywords


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


# ── User Sites ────────────────────────────────────────────────────────────────

def add_user_site(db_path: str, user_id: int, url: str, name: str) -> bool:
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO user_sites (user_id, url, name) VALUES (?, ?, ?)",
            (user_id, url, name),
        )
        return cursor.rowcount > 0


def remove_user_site(db_path: str, user_id: int, url: str) -> bool:
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM user_sites WHERE user_id = ? AND url = ?",
            (user_id, url),
        )
        return cursor.rowcount > 0


def get_user_sites(db_path: str, user_id: int) -> list[dict]:
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT url, name FROM user_sites WHERE user_id = ? ORDER BY name, url",
            (user_id,),
        ).fetchall()
        return [{"url": row["url"], "name": row["name"] or row["url"]} for row in rows]


def get_all_user_sites(db_path: str) -> dict[int, list[dict]]:
    """Returns {user_id: [{"url": ..., "name": ...}, ...]}"""
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, url, name FROM user_sites ORDER BY user_id"
        ).fetchall()

    result: dict[int, list[dict]] = {}
    for row in rows:
        uid = row["user_id"]
        if uid not in result:
            result[uid] = []
        result[uid].append({"url": row["url"], "name": row["name"] or row["url"]})
    return result
