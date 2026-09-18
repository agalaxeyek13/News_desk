"""
SQLite storage for article deduplication and history.
Thread-safe: uses a module-level Lock around all write operations.
"""

import sqlite3
import logging
import os
import threading

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "news.db")
_lock = threading.Lock()


def _get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the articles table if it doesn't exist. Add content column if missing."""
    with _lock:
        conn = _get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    published TEXT,
                    category TEXT,
                    content TEXT DEFAULT '',
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON articles(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON articles(scraped_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON articles(category)")
            conn.commit()
            # Add columns to existing DBs that predate this schema
            for col, definition in [
                ("content", "TEXT DEFAULT ''"),
                ("symbol", "TEXT DEFAULT ''"),
                ("sentiment", "TEXT DEFAULT ''"),
                ("thumbnail", "TEXT DEFAULT ''"),
                ("msid", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {definition}")
                    conn.commit()
                    logger.info("Migrated: added %s column", col)
                except sqlite3.OperationalError:
                    pass  # Column already exists
            logger.info("Database initialised at %s", DB_PATH)
        finally:
            conn.close()


def prune_old_articles(ttl_hours: int = 6) -> int:
    """
    Delete articles older than ttl_hours. Returns the number of rows deleted.
    Also runs VACUUM to reclaim disk space after large deletes.
    """
    with _lock:
        conn = _get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM articles WHERE scraped_at < datetime('now', ? || ' hours')",
                (f"-{ttl_hours}",),
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                conn.execute("VACUUM")
                conn.commit()
                logger.info("Pruned %d articles older than %dh", deleted, ttl_hours)
            return deleted
        except Exception as e:
            logger.error("Prune error: %s", e)
            return 0
        finally:
            conn.close()


def is_new(url):
    """Check if an article URL has NOT been seen before. Read-only, no lock needed."""
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,))
        return cursor.fetchone() is None
    finally:
        conn.close()


def mark_seen(article):
    """Insert an article into the database (thread-safe)."""
    with _lock:
        conn = _get_connection()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO articles
                   (title, url, source, published, category, content, symbol, sentiment, thumbnail, msid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    article["title"],
                    article["url"],
                    article["source"],
                    article["published"],
                    article.get("category", ""),
                    article.get("content", ""),
                    article.get("symbol", ""),
                    article.get("sentiment", ""),
                    article.get("thumbnail", ""),
                    article.get("msid", ""),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error("DB insert error: %s", e)
        finally:
            conn.close()


def get_recent(n=100):
    """Fetch the most recent N articles, newest first."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, symbol, sentiment, scraped_at
               FROM articles ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (n,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_article_count():
    """Return total number of stored articles."""
    conn = _get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM articles")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_recent_by_source(source, n=50):
    """Fetch the most recent N articles from a specific source, newest first."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, symbol, sentiment, scraped_at
               FROM articles WHERE source = ? ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (source, n),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_liveblogs(n=50):
    """Fetch the most recent N liveblog updates (category = '🔴 LIVE'), newest scraped first."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, symbol, sentiment, scraped_at
               FROM articles WHERE category = '🔴 LIVE'
               ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (n,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_scanx(n=100):
    """Get latest ScanX articles ordered by scraped_at (newest first)."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, symbol, sentiment, scraped_at
               FROM articles WHERE source = 'ScanX'
               ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (n,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_mc(n=100):
    """Get latest MoneyControl articles, newest scraped first."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, sentiment, scraped_at
               FROM articles WHERE source = 'MoneyControl'
               ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (n,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_et(n=100):
    """Get latest Economic Times articles, newest scraped first."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, sentiment, thumbnail, msid, scraped_at
               FROM articles WHERE source = 'Economic Times'
               ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (n,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_recent_et_by_category(category: str, n=50):
    """Get ET articles filtered by category, newest scraped first."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT title, url, source, published, category, content, sentiment, thumbnail, msid, scraped_at
               FROM articles WHERE source = 'Economic Times' AND category = ?
               ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (category, n),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_unanalyzed(limit: int = 50) -> list:
    """
    Return articles that have an empty sentiment field.
    ScanX articles that already have API-provided sentiment are excluded;
    ScanX category-page articles (empty sentiment) are included so the ML
    worker can fill them in.
    Returns a list of dicts with keys: id, title, content.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT id, title, content FROM articles
               WHERE (sentiment IS NULL OR sentiment = '')
               ORDER BY scraped_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_sentiment(article_id: int, sentiment: str) -> None:
    """Update the sentiment label for a single article by its primary key."""
    with _lock:
        conn = _get_connection()
        try:
            conn.execute(
                "UPDATE articles SET sentiment = ? WHERE id = ?",
                (sentiment, article_id),
            )
            conn.commit()
        except Exception as e:
            logger.error("update_sentiment error: %s", e)
        finally:
            conn.close()


def get_et_categories():
    """Return distinct ET categories with article counts, sorted by count desc."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT category, COUNT(*) AS count
               FROM articles WHERE source = 'Economic Times'
               GROUP BY category ORDER BY count DESC""",
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
