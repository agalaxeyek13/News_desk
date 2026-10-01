"""
Persistence for FDE cluster history — lets scorer.py tell whether a
story thread is new, growing, or holding steady day over day.

Lives in the same news.db SQLite file as storage/db.py (new table, no
interference with the existing articles table).
"""

import sqlite3
import logging
import threading
from datetime import date

from storage.db import DB_PATH

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_fde_db():
    """Create the fde_cluster_history and fde_sent_articles tables if missing."""
    with _lock:
        conn = _get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fde_cluster_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    entities TEXT NOT NULL,
                    article_count INTEGER NOT NULL,
                    source_count INTEGER NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fde_run_date ON fde_cluster_history(run_date)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fde_sent_articles (
                    url TEXT PRIMARY KEY,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            conn.close()


def filter_unsent(articles: list) -> list:
    """Drop any article whose URL has already been included in a past briefing."""
    conn = _get_connection()
    try:
        urls = [a["url"] for a in articles]
        if not urls:
            return []
        placeholders = ",".join("?" * len(urls))
        cursor = conn.execute(f"SELECT url FROM fde_sent_articles WHERE url IN ({placeholders})", urls)
        already_sent = {row["url"] for row in cursor.fetchall()}
        return [a for a in articles if a["url"] not in already_sent]
    finally:
        conn.close()


def mark_articles_sent(articles: list) -> None:
    """Record every article that went into a briefing that was actually sent."""
    with _lock:
        conn = _get_connection()
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO fde_sent_articles (url) VALUES (?)",
                [(a["url"],) for a in articles],
            )
            conn.commit()
        except Exception as e:
            logger.error("FDE store mark_articles_sent error: %s", e)
        finally:
            conn.close()


def save_cluster_snapshot(entities: set, article_count: int, source_count: int, run_date: str = None) -> None:
    """Record today's version of one cluster for tomorrow's trend comparison."""
    run_date = run_date or date.today().isoformat()
    with _lock:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT INTO fde_cluster_history (run_date, entities, article_count, source_count) VALUES (?, ?, ?, ?)",
                (run_date, ",".join(sorted(entities)), article_count, source_count),
            )
            conn.commit()
        except Exception as e:
            logger.error("FDE store insert error: %s", e)
        finally:
            conn.close()


def get_recent_snapshots(days: int = 3, before_date: str = None) -> list:
    """
    Return snapshots from the last `days` days, excluding `before_date`
    itself (defaults to today). Each row: {"entities": set, "article_count": int}.
    """
    before_date = before_date or date.today().isoformat()
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT entities, article_count FROM fde_cluster_history "
            "WHERE run_date < ? AND run_date >= date(?, ?) "
            "ORDER BY run_date DESC LIMIT 500",
            (before_date, before_date, f"-{days} days"),
        )
        rows = cursor.fetchall()
        return [
            {"entities": set(r["entities"].split(",")) if r["entities"] else set(), "article_count": r["article_count"]}
            for r in rows
        ]
    finally:
        conn.close()
