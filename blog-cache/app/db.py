import os
import random
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/blog.db"))
DB_DELAY_SECONDS = float(os.getenv("DB_DELAY_SECONDS", "0.05"))
SEED_ARTICLES = 200


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицу и заполняет её тестовыми статьями, если она пустая."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL,
                body       TEXT    NOT NULL,
                views      INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        (count,) = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        if count == 0:
            conn.executemany(
                "INSERT INTO articles (title, body, views) VALUES (?, ?, ?)",
                [
                    (f"Статья {i}", f"Текст статьи {i}. " * 50, random.randint(0, 10_000))
                    for i in range(1, SEED_ARTICLES + 1)
                ],
            )


def get_article(article_id: int) -> dict | None:
    time.sleep(DB_DELAY_SECONDS)
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    return dict(row) if row else None


def get_popular_articles(limit: int = 10) -> list[dict]:
    time.sleep(DB_DELAY_SECONDS)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, views FROM articles ORDER BY views DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def update_article(article_id: int, title: str, body: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE articles SET title = ?, body = ? WHERE id = ?", (title, body, article_id)
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    return dict(row)
