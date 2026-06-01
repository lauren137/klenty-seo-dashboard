"""SQLite-backed storage for tracked URLs and API response cache."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.db")
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_urls.json")


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS tracked_urls (
                path TEXT PRIMARY KEY,
                added_at INTEGER NOT NULL,
                label TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
    seed_if_empty()


def seed_if_empty():
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM tracked_urls").fetchone()[0]
        if n > 0:
            return
        if not os.path.exists(SEED_PATH):
            return
        with open(SEED_PATH) as f:
            urls = json.load(f)
        now = int(time.time())
        for u in urls:
            c.execute(
                "INSERT OR IGNORE INTO tracked_urls (path, added_at) VALUES (?, ?)",
                (u, now),
            )


def list_urls() -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT path FROM tracked_urls ORDER BY added_at ASC").fetchall()
    return [r["path"] for r in rows]


def add_url(path: str) -> bool:
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO tracked_urls (path, added_at) VALUES (?, ?)",
                (path, int(time.time())),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def remove_url(path: str):
    with _conn() as c:
        c.execute("DELETE FROM tracked_urls WHERE path = ?", (path,))


def cache_get(key: str):
    with _conn() as c:
        row = c.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    if row["expires_at"] < int(time.time()):
        return None
    return json.loads(row["value"])


def cache_set(key: str, value, ttl_seconds: int = 900):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), int(time.time()) + ttl_seconds),
        )


def cache_clear():
    with _conn() as c:
        c.execute("DELETE FROM cache")
