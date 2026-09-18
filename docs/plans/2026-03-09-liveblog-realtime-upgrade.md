# Liveblog Real-Time Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the News Alert System to near-real-time (~15s latency) by adding Al Jazeera GraphQL liveblog polling, auto-discovery of active liveblogs, thread-safe DB writes, and a redesigned dashboard with a LIVE column.

**Architecture:** Two parallel threads — a slow loop (RSS/HTML every 120s) and a fast loop (GraphQL liveblog every 15s). Both write to SQLite via a shared threading.Lock(). A new `content` column stores liveblog update body text. Flask gains `/api/news/live` and `/api/status` endpoints. The dashboard gains a third LIVE column with 10s auto-refresh.

**Tech Stack:** Python 3.12, requests, BeautifulSoup4, feedparser, Flask 3, SQLite3, threading, python-dotenv, lxml

---

## Pre-flight: Check existing state

```bash
ls /home/algolinux2/Documents/GitHub/News_scraper/
# Should show: alerts/ config.py dashboard/ main.py scrapers/ storage/ venv/
```

---

### Task 1: Upgrade requirements.txt and create .env.example

**Files:**
- Modify: `requirements.txt`
- Create: `.env.example`

**Step 1: Rewrite requirements.txt**

```
feedparser>=6.0.11
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
plyer>=2.1.0
flask>=3.0.0
python-dotenv>=1.0.0
```

**Step 2: Create .env.example**

```
POLL_INTERVAL_SECONDS=120
LIVEBLOG_POLL_INTERVAL_SECONDS=15
ENABLE_DESKTOP_NOTIFICATIONS=true
DASHBOARD_PORT=5050
```

**Step 3: Install new deps**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper
source venv/bin/activate
pip install python-dotenv lxml
```

Expected: Successfully installed python-dotenv and lxml (or "already satisfied")

**Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: pin requirements, add python-dotenv + lxml, add .env.example"
```

---

### Task 2: Upgrade config.py with liveblog settings and dotenv support

**Files:**
- Modify: `config.py`

**Step 1: Rewrite config.py**

Replace the entire file with:

```python
"""
Configuration for the News Alert System.
Loads overrides from .env if present.
"""
from dotenv import load_dotenv
import os

load_dotenv()

# Poll intervals
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", 120))
LIVEBLOG_POLL_INTERVAL_SECONDS = int(os.getenv("LIVEBLOG_POLL_INTERVAL_SECONDS", 15))

# Desktop notification settings
ENABLE_DESKTOP_NOTIFICATIONS = os.getenv("ENABLE_DESKTOP_NOTIFICATIONS", "true").lower() == "true"
NOTIFICATION_TIMEOUT = 10  # seconds

# Dashboard settings
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 5050))

# Data sources
ALJAZEERA_RSS_URL = "https://www.aljazeera.com/xml/rss/all.xml"
REUTERS_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"
ALJAZEERA_GRAPHQL_URL = "https://www.aljazeera.com/graphql"

# Liveblog settings
TRACKED_LIVEBLOG_SLUGS = []           # Manually tracked slugs (auto-discovery adds to these)
ENABLE_LIVEBLOG_AUTO_DISCOVERY = True # Auto-find active liveblogs from homepage

# Database
DB_PATH = "news.db"

# Max articles to show on dashboard
MAX_DASHBOARD_ARTICLES = 100

# Retry / resilience settings
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 20

# Notification settings
ENABLE_SOUND_ALERT = False
MIN_NOTIFICATION_INTERVAL_SECONDS = 2
```

**Step 2: Verify import works**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "import config; print(config.LIVEBLOG_POLL_INTERVAL_SECONDS)"
```

Expected: `15`

**Step 3: Commit**

```bash
git add config.py
git commit -m "feat: upgrade config with liveblog settings and dotenv support"
```

---

### Task 3: Create utils/http.py — retry-capable HTTP helper

**Files:**
- Create: `utils/__init__.py`
- Create: `utils/http.py`

**Step 1: Create utils/__init__.py** (empty file)

**Step 2: Create utils/http.py**

```python
"""
Retry-capable HTTP helper for all scrapers.
"""
import requests
import time
import logging

logger = logging.getLogger(__name__)


def get_with_retry(url, headers, timeout=20, max_retries=3, backoff=5):
    """
    GET a URL with automatic retries on failure.
    Raises the last exception if all retries are exhausted.
    """
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, max_retries, e, backoff
                )
                time.sleep(backoff)
            else:
                raise
```

**Step 3: Verify import**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "from utils.http import get_with_retry; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add utils/__init__.py utils/http.py
git commit -m "feat: add utils/http.py with retry-capable get_with_retry helper"
```

---

### Task 4: Create scrapers/liveblog.py — GraphQL liveblog scraper

**Files:**
- Create: `scrapers/liveblog.py`

**Step 1: Create scrapers/liveblog.py**

```python
"""
Al Jazeera GraphQL liveblog scraper.

Polls the AJ GraphQL API for liveblog updates every 15s (called from main.py fast loop).
Uses three operations:
  - SingleLiveBlogChildrensQuery  → get all update post IDs for a liveblog slug
  - LiveBlogUpdateQuery           → fetch full content of a single update by post ID
  - ArchipelagoSingleLiveBlogQuery → get liveblog metadata (date, slug)
"""

import time
import logging
import json
from bs4 import BeautifulSoup

from config import ALJAZEERA_GRAPHQL_URL, REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_BACKOFF_SECONDS
from utils.http import get_with_retry

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.aljazeera.com/",
}

# Module-level set of seen post IDs per slug: { slug: set(post_ids) }
_seen_post_ids: dict[str, set] = {}


def _gql(operation_name: str, variables: dict) -> dict | None:
    """Call the AJ GraphQL endpoint and return parsed JSON, or None on error."""
    url = (
        f"{ALJAZEERA_GRAPHQL_URL}"
        f"?wp-site=aje"
        f"&operationName={operation_name}"
        f"&variables={json.dumps(variables, separators=(',', ':'))}"
        f"&extensions={{}}"
    )
    try:
        resp = get_with_retry(
            url, HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
            backoff=RETRY_BACKOFF_SECONDS,
        )
        return resp.json()
    except Exception as e:
        logger.error("GraphQL %s failed: %s", operation_name, e)
        return None


def _get_children_ids(slug: str) -> list[int]:
    """Return list of post IDs for all updates in a liveblog."""
    data = _gql("SingleLiveBlogChildrensQuery", {"postName": slug})
    if not data:
        return []
    try:
        nodes = data["data"]["post"]["children"]["nodes"]
        return [node["databaseId"] for node in nodes if "databaseId" in node]
    except (KeyError, TypeError) as e:
        logger.debug("Could not parse children for %s: %s", slug, e)
        return []


def _get_liveblog_meta(slug: str) -> dict:
    """Return {'year': str, 'month': str, 'day': str} for URL construction."""
    data = _gql("ArchipelagoSingleLiveBlogQuery", {
        "name": slug,
        "postType": "liveblog",
        "preview": "",
    })
    meta = {"year": "2025", "month": "01", "day": "01"}
    if not data:
        return meta
    try:
        post = data["data"]["post"]
        date_str = post.get("date", "")  # e.g. "2025-10-12T14:30:00"
        if date_str and "T" in date_str:
            parts = date_str.split("T")[0].split("-")
            meta["year"], meta["month"], meta["day"] = parts[0], parts[1], parts[2]
    except (KeyError, TypeError):
        pass
    return meta


def _get_update(post_id: int) -> dict | None:
    """Fetch full content of a single liveblog update."""
    data = _gql("LiveBlogUpdateQuery", {
        "postID": post_id,
        "postType": "liveblog-update",
        "preview": "",
        "isAmp": False,
    })
    if not data:
        return None
    try:
        post = data["data"]["post"]
        title = post.get("title", "").strip()
        published = post.get("date", "")
        if published and "T" in published:
            published = published.replace("T", " ")[:19]

        # Strip HTML from content
        raw_html = post.get("content", "") or ""
        content = BeautifulSoup(raw_html, "lxml").get_text(separator=" ", strip=True)

        return {
            "title": title,
            "content": content,
            "published": published,
        }
    except (KeyError, TypeError) as e:
        logger.debug("Could not parse update %d: %s", post_id, e)
        return None


def scrape(slug: str) -> list[dict]:
    """
    Fetch new liveblog updates for a given slug.
    Only returns updates not yet seen (tracked in module-level _seen_post_ids).

    Returns list of article dicts: {title, url, source, published, category, content}
    """
    if slug not in _seen_post_ids:
        _seen_post_ids[slug] = set()

    post_ids = _get_children_ids(slug)
    if not post_ids:
        return []

    new_ids = [pid for pid in post_ids if pid not in _seen_post_ids[slug]]
    if not new_ids:
        return []

    # Get liveblog meta once for URL construction
    meta = _get_liveblog_meta(slug)

    articles = []
    for post_id in new_ids:
        update = _get_update(post_id)
        if update and update.get("title"):
            url = (
                f"https://www.aljazeera.com/news/liveblog/"
                f"{meta['year']}/{meta['month']}/{meta['day']}"
                f"/{slug}?update={post_id}"
            )
            articles.append({
                "title": update["title"],
                "url": url,
                "source": "Al Jazeera",
                "published": update["published"],
                "category": "🔴 LIVE",
                "content": update["content"],
            })
        _seen_post_ids[slug].add(post_id)
        time.sleep(0.3)  # Rate limiting between individual update fetches

    if articles:
        logger.info("Liveblog [%s]: %d new updates", slug, len(articles))
    return articles


def reset_seen(slug: str | None = None):
    """Reset seen state. Used in tests. If slug is None, resets all."""
    global _seen_post_ids
    if slug is None:
        _seen_post_ids = {}
    elif slug in _seen_post_ids:
        del _seen_post_ids[slug]
```

**Step 2: Verify import**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "from scrapers.liveblog import scrape; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add scrapers/liveblog.py
git commit -m "feat: add scrapers/liveblog.py — AJ GraphQL liveblog scraper"
```

---

### Task 5: Create scrapers/liveblog_discovery.py — auto-discovery of active liveblogs

**Files:**
- Create: `scrapers/liveblog_discovery.py`

**Step 1: Create scrapers/liveblog_discovery.py**

```python
"""
Auto-discovers active Al Jazeera liveblogs from:
1. AJ homepage HTML (links matching /liveblog/)
2. GraphQL ArchipelagoBreakingTickerQuery (breaking/live news ticker)
"""

import re
import logging
import json

import requests
from bs4 import BeautifulSoup

from config import ALJAZEERA_GRAPHQL_URL, REQUEST_TIMEOUT_SECONDS
from utils.http import get_with_retry

logger = logging.getLogger(__name__)

ALJAZEERA_HOME_URL = "https://www.aljazeera.com/"
LIVEBLOG_SLUG_RE = re.compile(r"/liveblog/\d{4}/\d{2}/\d{2}/([^/?#]+)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.aljazeera.com/",
}

GQL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.aljazeera.com/",
}


def _slugs_from_homepage() -> set[str]:
    """Scrape AJ homepage HTML and extract liveblog slugs from URLs."""
    slugs = set()
    try:
        resp = get_with_retry(ALJAZEERA_HOME_URL, HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            m = LIVEBLOG_SLUG_RE.search(href)
            if m:
                slugs.add(m.group(1))
        logger.info("Discovery (HTML): found %d liveblog slugs", len(slugs))
    except Exception as e:
        logger.error("Homepage discovery failed: %s", e)
    return slugs


def _slugs_from_breaking_ticker() -> set[str]:
    """Query AJ GraphQL breaking ticker for any live items."""
    slugs = set()
    url = (
        f"{ALJAZEERA_GRAPHQL_URL}"
        f"?wp-site=aje"
        f"&operationName=ArchipelagoBreakingTickerQuery"
        f"&variables={{}}"
        f"&extensions={{}}"
    )
    try:
        resp = get_with_retry(url, GQL_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        data = resp.json()
        nodes = data.get("data", {}).get("breakingTicker", {}).get("nodes", [])
        for node in nodes:
            uri = node.get("uri", "")
            m = LIVEBLOG_SLUG_RE.search(uri)
            if m:
                slugs.add(m.group(1))
        logger.info("Discovery (ticker): found %d liveblog slugs", len(slugs))
    except Exception as e:
        logger.error("Breaking ticker discovery failed: %s", e)
    return slugs


def discover() -> list[str]:
    """
    Discover all currently active liveblog slugs.
    Merges results from homepage HTML and breaking ticker.
    Returns a sorted list of unique slugs.
    """
    slugs = _slugs_from_homepage() | _slugs_from_breaking_ticker()
    return sorted(slugs)
```

**Step 2: Verify import**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "from scrapers.liveblog_discovery import discover; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add scrapers/liveblog_discovery.py
git commit -m "feat: add scrapers/liveblog_discovery.py — homepage + ticker liveblog auto-discovery"
```

---

### Task 6: Update scrapers/__init__.py

**Files:**
- Modify: `scrapers/__init__.py`

**Step 1: Update scrapers/__init__.py**

```python
from scrapers import aljazeera, reuters, liveblog, liveblog_discovery

__all__ = ["aljazeera", "reuters", "liveblog", "liveblog_discovery"]
```

**Step 2: Verify**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "from scrapers import liveblog, liveblog_discovery; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add scrapers/__init__.py
git commit -m "chore: export liveblog scrapers from scrapers/__init__.py"
```

---

### Task 7: Upgrade storage/db.py — thread safety + content column + liveblogs query

**Files:**
- Modify: `storage/db.py`

**Step 1: Rewrite storage/db.py**

```python
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
            # Add content column to existing DBs that predate this schema
            try:
                conn.execute("ALTER TABLE articles ADD COLUMN content TEXT DEFAULT ''")
                conn.commit()
                logger.info("Migrated: added content column")
            except sqlite3.OperationalError:
                pass  # Column already exists
            logger.info("Database initialised at %s", DB_PATH)
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
                   (title, url, source, published, category, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    article["title"],
                    article["url"],
                    article["source"],
                    article["published"],
                    article.get("category", ""),
                    article.get("content", ""),
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
            """SELECT title, url, source, published, category, content, scraped_at
               FROM articles ORDER BY published DESC, id DESC LIMIT ?""",
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
            """SELECT title, url, source, published, category, content, scraped_at
               FROM articles WHERE source = ? ORDER BY published DESC, id DESC LIMIT ?""",
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
            """SELECT title, url, source, published, category, content, scraped_at
               FROM articles WHERE category = '🔴 LIVE'
               ORDER BY scraped_at DESC, id DESC LIMIT ?""",
            (n,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
```

**Step 2: Verify import**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "from storage.db import init_db, get_recent_liveblogs; init_db(); print('OK')"
```

Expected: `OK` (may also print "Migrated: added content column" if DB exists)

**Step 3: Commit**

```bash
git add storage/db.py
git commit -m "feat: upgrade db.py — thread safety, content column, get_recent_liveblogs()"
```

---

### Task 8: Upgrade main.py — dual poll loops (slow + fast)

**Files:**
- Modify: `main.py`

**Step 1: Rewrite main.py**

```python
#!/usr/bin/env python3
"""
📰 News Alert System — Main Entry Point
Runs two poll loops:
  - Slow loop: RSS + HTML every POLL_INTERVAL_SECONDS (120s)
  - Fast loop: GraphQL liveblogs every LIVEBLOG_POLL_INTERVAL_SECONDS (15s)
"""

import sys
import os
import time
import logging
import threading
import signal
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    POLL_INTERVAL_SECONDS,
    LIVEBLOG_POLL_INTERVAL_SECONDS,
    ENABLE_DESKTOP_NOTIFICATIONS,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    TRACKED_LIVEBLOG_SLUGS,
    ENABLE_LIVEBLOG_AUTO_DISCOVERY,
)
from scrapers import aljazeera, reuters
from scrapers.liveblog import scrape as scrape_liveblog
from scrapers.liveblog_discovery import discover as discover_liveblogs
from storage.db import init_db, is_new, mark_seen
from alerts.notifier import notify_new_article, notify_scrape_summary, notify_startup
from dashboard.app import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

running = True

# Shared state for /api/status — updated after each cycle
last_scrape_time: datetime | None = None
tracked_slugs: list[str] = list(TRACKED_LIVEBLOG_SLUGS)
_slugs_lock = threading.Lock()


def signal_handler(sig, frame):
    global running
    print("\n\n🛑 Shutting down gracefully...")
    running = False
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def _process_articles(articles: list[dict]) -> int:
    """Dedup, store, and notify for a batch of articles. Returns new count."""
    new_count = 0
    for article in articles:
        if is_new(article["url"]):
            new_count += 1
            mark_seen(article)
            notify_new_article(article, enable_desktop=ENABLE_DESKTOP_NOTIFICATIONS)
    return new_count


def scrape_cycle():
    """Run one slow scrape cycle (RSS + HTML sources)."""
    global last_scrape_time
    all_articles = []

    try:
        all_articles.extend(aljazeera.scrape())
    except Exception as e:
        logger.error("Al Jazeera scrape failed: %s", e)

    try:
        all_articles.extend(reuters.scrape())
    except Exception as e:
        logger.error("Reuters scrape failed: %s", e)

    new_count = _process_articles(all_articles)
    notify_scrape_summary(new_count, len(all_articles))
    last_scrape_time = datetime.now(timezone.utc)
    return new_count


def liveblog_cycle():
    """Run one fast scrape cycle (GraphQL liveblogs only)."""
    global last_scrape_time
    with _slugs_lock:
        slugs = list(tracked_slugs)

    total_new = 0
    for slug in slugs:
        try:
            articles = scrape_liveblog(slug)
            total_new += _process_articles(articles)
        except Exception as e:
            logger.error("Liveblog scrape failed [%s]: %s", slug, e)

    if total_new > 0:
        logger.info("Liveblog cycle: %d new updates across %d liveblogs", total_new, len(slugs))
    last_scrape_time = datetime.now(timezone.utc)
    return total_new


def poll_loop():
    """Slow loop: RSS + HTML every POLL_INTERVAL_SECONDS."""
    global running
    logger.info("🚀 Slow poll loop started (interval: %ds)", POLL_INTERVAL_SECONDS)
    scrape_cycle()
    while running:
        time.sleep(POLL_INTERVAL_SECONDS)
        if not running:
            break
        try:
            scrape_cycle()
        except Exception as e:
            logger.error("Slow scrape cycle error: %s", e)


def liveblog_poll_loop():
    """Fast loop: GraphQL liveblogs every LIVEBLOG_POLL_INTERVAL_SECONDS. Re-discovers every 5 min."""
    global running, tracked_slugs
    logger.info("⚡ Fast liveblog loop started (interval: %ds)", LIVEBLOG_POLL_INTERVAL_SECONDS)

    last_discovery = 0.0

    while running:
        now = time.time()
        # Re-run auto-discovery every 5 minutes
        if ENABLE_LIVEBLOG_AUTO_DISCOVERY and (now - last_discovery) > 300:
            try:
                discovered = discover_liveblogs()
                with _slugs_lock:
                    existing = set(tracked_slugs)
                    new_slugs = [s for s in discovered if s not in existing]
                    if new_slugs:
                        tracked_slugs.extend(new_slugs)
                        logger.info("Auto-discovered %d new liveblog(s): %s", len(new_slugs), new_slugs)
                last_discovery = time.time()
            except Exception as e:
                logger.error("Liveblog auto-discovery error: %s", e)

        liveblog_cycle()
        time.sleep(LIVEBLOG_POLL_INTERVAL_SECONDS)


def main():
    """Main entry point."""
    notify_startup()
    init_db()
    logger.info("📦 Database ready")

    # Slow loop thread
    slow_thread = threading.Thread(target=poll_loop, daemon=True)
    slow_thread.start()
    logger.info("🔄 Slow scraper thread started")

    # Fast liveblog loop thread
    fast_thread = threading.Thread(target=liveblog_poll_loop, daemon=True)
    fast_thread.start()
    logger.info("⚡ Fast liveblog thread started")

    logger.info("🌐 Dashboard starting at http://localhost:%d", DASHBOARD_PORT)
    print(f"\n   🌐 Open http://localhost:{DASHBOARD_PORT} in your browser\n")

    app.run(
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
```

**Step 2: Verify import (dry run)**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "import main; print('OK')"
```

Expected: `OK` (may print startup banner but no crash)

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add dual poll loops to main.py — slow RSS + fast liveblog GraphQL"
```

---

### Task 9: Upgrade dashboard/app.py — add /api/news/live and /api/status endpoints

**Files:**
- Modify: `dashboard/app.py`

**Step 1: Rewrite dashboard/app.py**

```python
"""
Flask web dashboard for the News Alert System.
Serves a live-updating news feed at http://localhost:5050
"""

from flask import Flask, render_template, jsonify, request
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import get_recent, get_article_count, get_recent_by_source, get_recent_liveblogs

app = Flask(__name__)


def _get_tracked_slug_count():
    """Import tracked_slugs from main at runtime to avoid circular import."""
    try:
        import main as m
        return len(m.tracked_slugs)
    except Exception:
        return 0


def _get_last_scrape_time():
    """Import last_scrape_time from main at runtime to avoid circular import."""
    try:
        import main as m
        if m.last_scrape_time:
            return m.last_scrape_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/news")
def api_news():
    source = request.args.get("source", None)
    if source:
        articles = get_recent_by_source(source, 50)
    else:
        articles = get_recent(100)
    return jsonify({"articles": articles, "total": get_article_count()})


@app.route("/api/news/grouped")
def api_news_grouped():
    aljazeera = get_recent_by_source("Al Jazeera", 50)
    reuters = get_recent_by_source("Reuters", 50)
    return jsonify({
        "aljazeera": aljazeera,
        "reuters": reuters,
        "total": get_article_count(),
    })


@app.route("/api/news/live")
def api_live():
    """Return only liveblog updates (category = 🔴 LIVE), newest first."""
    articles = get_recent_liveblogs(100)
    return jsonify({"articles": articles, "total": len(articles)})


@app.route("/api/status")
def api_status():
    """Return system health/status info."""
    return jsonify({
        "status": "running",
        "total_articles": get_article_count(),
        "tracked_liveblogs": _get_tracked_slug_count(),
        "last_scrape": _get_last_scrape_time(),
    })
```

**Step 2: Verify Flask routes load**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "from dashboard.app import app; print([str(r) for r in app.url_map.iter_rules()])"
```

Expected: Output includes `/api/news/live` and `/api/status`

**Step 3: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add /api/news/live and /api/status endpoints to dashboard"
```

---

### Task 10: Redesign dashboard/templates/index.html — LIVE column, filter bar, 10s refresh

**Files:**
- Modify: `dashboard/templates/index.html`

**Step 1: Replace index.html**

Replace the entire file with the following (key changes: 3-column grid, LIVE section, 10s refresh for live, filter bar, status polling, content snippet in live cards, pulse animation):

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📰 News Alert System — Live Feed</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a2e;
            --bg-card-hover: #1e1e35;
            --text-primary: #e8e8f0;
            --text-secondary: #9898b0;
            --text-muted: #6868a0;
            --accent-aljazeera: #ff6b35;
            --accent-reuters: #ff8c00;
            --accent-blue: #4a7dff;
            --accent-green: #00d4aa;
            --accent-live: #ff2244;
            --border-color: #2a2a40;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        body::before {
            content: '';
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: radial-gradient(ellipse at 20% 50%, rgba(74,125,255,0.03) 0%, transparent 50%),
                        radial-gradient(ellipse at 80% 20%, rgba(255,107,53,0.03) 0%, transparent 50%);
            pointer-events: none; z-index: 0;
        }
        .container { max-width: 1600px; margin: 0 auto; padding: 0 20px; position: relative; z-index: 1; }

        /* Header */
        .header { padding: 30px 0 20px; text-align: center; border-bottom: 1px solid var(--border-color); margin-bottom: 16px; }
        .header h1 { font-size: 1.8rem; font-weight: 800; background: linear-gradient(135deg, var(--accent-blue), var(--accent-green)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 6px; }
        .header .subtitle { font-size: 0.85rem; color: var(--text-muted); }
        .top-bar { display: flex; justify-content: center; align-items: center; gap: 16px; margin: 12px 0 0; flex-wrap: wrap; }
        .stat { display: flex; align-items: center; gap: 6px; padding: 6px 14px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 100px; font-size: 0.78rem; }
        .stat .dot { width: 7px; height: 7px; border-radius: 50%; animation: pulse 2s ease-in-out infinite; }
        .dot.live { background: var(--accent-green); }
        .stat .value { font-weight: 600; }
        .last-scrape { font-size: 0.72rem; color: var(--text-muted); }

        @keyframes pulse { 0%,100% { opacity:1; transform:scale(1) } 50% { opacity:.5; transform:scale(.8) } }
        @keyframes livePulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,34,68,0.4) } 50% { box-shadow: 0 0 0 8px rgba(255,34,68,0) } }
        @keyframes fadeIn { to { opacity:1; transform:translateY(0); } }

        /* Filter bar */
        .filter-bar { display: flex; justify-content: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
        .filter-btn { padding: 6px 18px; border-radius: 100px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-secondary); font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }
        .filter-btn:hover { border-color: var(--accent-blue); color: var(--text-primary); }
        .filter-btn.active { background: var(--accent-blue); border-color: var(--accent-blue); color: #fff; }
        .filter-btn.live-btn.active { background: var(--accent-live); border-color: var(--accent-live); }

        .refresh-bar { text-align: center; margin-bottom: 16px; font-size: 0.75rem; color: var(--text-muted); }
        .refresh-bar .cd { color: var(--accent-blue); font-weight: 600; }

        /* Columns */
        .columns { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; padding-bottom: 40px; }
        .column { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 16px; overflow: hidden; }
        .column.hidden { display: none; }

        .column-header { padding: 16px 20px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--border-color); position: sticky; top: 0; z-index: 2; }
        .column-header.aljazeera { background: linear-gradient(135deg, rgba(255,107,53,0.12), rgba(255,107,53,0.04)); }
        .column-header.reuters { background: linear-gradient(135deg, rgba(255,140,0,0.12), rgba(255,140,0,0.04)); }
        .column-header.live-header { background: linear-gradient(135deg, rgba(255,34,68,0.15), rgba(255,34,68,0.04)); }
        .column-header.live-header.pulsing { animation: livePulse 1s ease-out 3; }

        .source-icon { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; font-weight: 700; }
        .source-icon.aj { background: var(--accent-aljazeera); color: #fff; }
        .source-icon.rt { background: var(--accent-reuters); color: #fff; }
        .source-icon.lv { background: var(--accent-live); color: #fff; font-size: 0.85rem; }
        .column-header h2 { font-size: 1rem; font-weight: 700; }
        .column-header .count { margin-left: auto; font-size: 0.75rem; color: var(--text-muted); background: var(--bg-primary); padding: 3px 10px; border-radius: 100px; }

        .article-list { padding: 8px; max-height: 75vh; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border-color) transparent; }
        .article-list::-webkit-scrollbar { width: 5px; }
        .article-list::-webkit-scrollbar-track { background: transparent; }
        .article-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 4px; }

        .article-card { display: block; text-decoration: none; color: inherit; padding: 14px 16px; border-radius: 10px; border: 1px solid transparent; transition: all 0.2s ease; margin-bottom: 4px; opacity: 0; transform: translateY(10px); animation: fadeIn 0.4s ease-out forwards; }
        .article-card:hover { background: var(--bg-card); border-color: var(--border-color); transform: translateY(-1px); }
        .article-card.fresh { border-left: 3px solid var(--accent-green); }
        .article-card.live-card.fresh { border-left: 3px solid var(--accent-live); }

        .article-card .meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .article-card .cat { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding: 2px 8px; border-radius: 4px; }
        .cat.aj { background: rgba(255,107,53,0.12); color: var(--accent-aljazeera); }
        .cat.rt { background: rgba(255,140,0,0.12); color: var(--accent-reuters); }
        .cat.lv { background: rgba(255,34,68,0.15); color: var(--accent-live); }
        .article-card .time { font-size: 0.7rem; color: var(--text-muted); margin-left: auto; }
        .article-card .title { font-size: 0.92rem; font-weight: 600; line-height: 1.45; }
        .article-card .snippet { font-size: 0.78rem; color: var(--text-secondary); margin-top: 5px; line-height: 1.4; }

        .empty-col { text-align: center; padding: 40px 20px; color: var(--text-muted); font-size: 0.85rem; }

        @media (max-width: 1024px) { .columns { grid-template-columns: 1fr 1fr; } }
        @media (max-width: 600px) { .columns { grid-template-columns: 1fr; } .header h1 { font-size: 1.4rem; } .article-list { max-height: 60vh; } }
    </style>
</head>
<body>
<div class="container">
    <header class="header">
        <h1>📰 News Alert System</h1>
        <p class="subtitle">Live headlines from Al Jazeera, Reuters & 🔴 Live Liveblogs</p>
        <div class="top-bar">
            <div class="stat">
                <span class="dot live"></span>
                <span>Status: <span class="value" id="status">Connecting...</span></span>
            </div>
            <div class="stat">
                <span>Total: <span class="value" id="total">—</span></span>
            </div>
            <div class="stat">
                <span>Live blogs: <span class="value" id="live-count">—</span></span>
            </div>
            <span class="last-scrape" id="last-scrape"></span>
        </div>
    </header>

    <div class="filter-bar">
        <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">All</button>
        <button class="filter-btn" data-filter="aj" onclick="setFilter('aj')">Al Jazeera</button>
        <button class="filter-btn" data-filter="rt" onclick="setFilter('rt')">Reuters</button>
        <button class="filter-btn live-btn" data-filter="lv" onclick="setFilter('lv')">🔴 Live</button>
    </div>

    <div class="refresh-bar">Auto-refresh in <span class="cd" id="cd">10</span>s</div>

    <div class="columns">
        <div class="column" id="col-aj">
            <div class="column-header aljazeera">
                <div class="source-icon aj">AJ</div>
                <h2>Al Jazeera</h2>
                <span class="count" id="aj-count">0 articles</span>
            </div>
            <div class="article-list" id="aj-feed">
                <div class="empty-col">⏳ Loading Al Jazeera headlines...</div>
            </div>
        </div>
        <div class="column" id="col-rt">
            <div class="column-header reuters">
                <div class="source-icon rt">R</div>
                <h2>Reuters</h2>
                <span class="count" id="rt-count">0 articles</span>
            </div>
            <div class="article-list" id="rt-feed">
                <div class="empty-col">⏳ Loading Reuters headlines...</div>
            </div>
        </div>
        <div class="column" id="col-lv">
            <div class="column-header live-header" id="live-header">
                <div class="source-icon lv">🔴</div>
                <h2>Live Updates</h2>
                <span class="count" id="lv-count">0 updates</span>
            </div>
            <div class="article-list" id="lv-feed">
                <div class="empty-col">📡 Watching for live updates...</div>
            </div>
        </div>
    </div>
</div>

<script>
    const REFRESH = 10;
    let cd = REFRESH;
    let knownUrls = new Set();
    let firstLoad = true;
    let currentFilter = 'all';

    function fmtTime(t) {
        if (!t) return '';
        try {
            const d = new Date(t);
            if (isNaN(d.getTime())) return t;
            const s = (Date.now() - d) / 1000;
            if (s < 60) return 'Just now';
            if (s < 3600) return Math.floor(s / 60) + 'm ago';
            if (s < 86400) return Math.floor(s / 3600) + 'h ago';
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        } catch { return t; }
    }

    function card(a, type, fresh) {
        const snippet = (type === 'lv' && a.content)
            ? `<div class="snippet">${a.content.substring(0, 200)}${a.content.length > 200 ? '…' : ''}</div>`
            : '';
        return `<a href="${a.url}" target="_blank" rel="noopener"
            class="article-card${type === 'lv' ? ' live-card' : ''}${fresh ? ' fresh' : ''}">
            <div class="meta">
                <span class="cat ${type}">${a.category || 'News'}</span>
                <span class="time">${fmtTime(a.published || a.scraped_at)}</span>
            </div>
            <div class="title">${a.title}</div>
            ${snippet}
        </a>`;
    }

    function renderList(articles, containerId, type) {
        const el = document.getElementById(containerId);
        if (!articles || articles.length === 0) {
            el.innerHTML = '<div class="empty-col">📡 No articles yet...</div>';
            return 0;
        }
        let html = '';
        let newCount = 0;
        articles.forEach(a => {
            const fresh = !knownUrls.has(a.url) && !firstLoad;
            if (fresh) newCount++;
            knownUrls.add(a.url);
            html += card(a, type, fresh);
        });
        el.innerHTML = html;
        el.querySelectorAll('.article-card').forEach((c, i) => { c.style.animationDelay = i * 0.03 + 's'; });
        return newCount;
    }

    function setFilter(f) {
        currentFilter = f;
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
        document.getElementById('col-aj').classList.toggle('hidden', f !== 'all' && f !== 'aj');
        document.getElementById('col-rt').classList.toggle('hidden', f !== 'all' && f !== 'rt');
        document.getElementById('col-lv').classList.toggle('hidden', f !== 'all' && f !== 'lv');
    }

    async function fetchNews() {
        try {
            const [groupedResp, liveResp] = await Promise.all([
                fetch('/api/news/grouped'),
                fetch('/api/news/live'),
            ]);
            const grouped = await groupedResp.json();
            const live = await liveResp.json();

            document.getElementById('status').textContent = 'Live';
            document.getElementById('total').textContent = grouped.total;
            document.getElementById('aj-count').textContent = (grouped.aljazeera || []).length + ' articles';
            document.getElementById('rt-count').textContent = (grouped.reuters || []).length + ' articles';
            document.getElementById('lv-count').textContent = (live.articles || []).length + ' updates';

            renderList(grouped.aljazeera, 'aj-feed', 'aj');
            renderList(grouped.reuters, 'rt-feed', 'rt');
            const newLive = renderList(live.articles, 'lv-feed', 'lv');

            // Pulse the LIVE header if new updates arrived
            if (newLive > 0) {
                const hdr = document.getElementById('live-header');
                hdr.classList.remove('pulsing');
                void hdr.offsetWidth; // reflow to restart animation
                hdr.classList.add('pulsing');
            }
            firstLoad = false;
        } catch (e) {
            console.error(e);
            document.getElementById('status').textContent = 'Reconnecting...';
        }
    }

    async function fetchStatus() {
        try {
            const r = await fetch('/api/status');
            const d = await r.json();
            document.getElementById('live-count').textContent = d.tracked_liveblogs ?? '—';
            if (d.last_scrape) {
                document.getElementById('last-scrape').textContent = 'Last scraped: ' + d.last_scrape;
            }
        } catch {}
    }

    function tick() {
        cd--;
        if (cd <= 0) { cd = REFRESH; fetchNews(); }
        document.getElementById('cd').textContent = cd;
    }

    fetchNews();
    fetchStatus();
    setInterval(tick, 1000);
    setInterval(fetchStatus, 30000);
</script>
</body>
</html>
```

**Step 2: Verify Flask can render template**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "
from dashboard.app import app
with app.test_client() as c:
    r = c.get('/')
    print('Status:', r.status_code)
    print('Has Live column:', b'Live Updates' in r.data)
"
```

Expected:
```
Status: 200
Has Live column: True
```

**Step 3: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: redesign dashboard — 3-column layout, LIVE section, filter bar, 10s refresh"
```

---

### Task 11: Create README.md

**Files:**
- Create: `README.md`

**Step 1: Create README.md**

```markdown
# 📰 News Alert System

A production-grade, near-real-time news monitoring dashboard that tracks Al Jazeera and Reuters, with special support for Al Jazeera **liveblogs** via direct GraphQL API polling (latency ~15 seconds).

## Features

- **Real-time liveblog tracking** — polls Al Jazeera's GraphQL API every 15s for liveblog updates
- **Auto-discovery** — automatically finds active liveblogs from the AJ homepage and breaking ticker
- **Al Jazeera RSS + HTML** — full article feed via RSS with homepage HTML fallback
- **Reuters** — multi-category feed via Google News RSS proxy
- **Live dashboard** — 3-column responsive web UI with 10s auto-refresh LIVE section
- **Filter bar** — filter by All / Al Jazeera / Reuters / 🔴 Live
- **Desktop notifications** — via plyer (optional)
- **Thread-safe SQLite storage** — dual poll loops writing concurrently

## Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and edit as needed:

```bash
cp .env.example .env
```

To manually track a specific liveblog, add its slug to `TRACKED_LIVEBLOG_SLUGS` in `config.py`:

```python
TRACKED_LIVEBLOG_SLUGS = ["iran-war-live-mojtaba-khamenei-named-supreme-leader-israel-bombs-tehran"]
```

Or let auto-discovery handle it — it checks every 5 minutes.

## Running

```bash
python main.py
```

Open **http://localhost:5050** in your browser.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   main.py                        │
│                                                  │
│  ┌──────────────────┐  ┌────────────────────┐   │
│  │  Slow Loop (120s) │  │ Fast Loop (15s)    │   │
│  │  aljazeera.scrape │  │ liveblog.scrape    │   │
│  │  reuters.scrape   │  │ liveblog_discovery │   │
│  └────────┬─────────┘  └────────┬───────────┘   │
│           └──────────┬──────────┘               │
│                      ▼                           │
│              storage/db.py (SQLite + Lock)       │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
           dashboard/app.py (Flask)
                      │
                      ▼
          http://localhost:5050
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/news` | All recent articles |
| `GET /api/news/grouped` | Grouped by source |
| `GET /api/news/live` | Liveblog updates only |
| `GET /api/status` | System health/status |
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README.md with architecture diagram and usage instructions"
```

---

### Task 12: Final integration smoke test

**Step 1: Verify all imports resolve**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "
import config
from utils.http import get_with_retry
from scrapers.liveblog import scrape, reset_seen
from scrapers.liveblog_discovery import discover
from storage.db import init_db, is_new, mark_seen, get_recent_liveblogs
from dashboard.app import app
print('All imports OK')
"
```

Expected: `All imports OK`

**Step 2: Verify DB schema**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "
from storage.db import init_db, _get_connection
init_db()
conn = _get_connection()
cursor = conn.execute('PRAGMA table_info(articles)')
cols = [row[1] for row in cursor.fetchall()]
print('Columns:', cols)
assert 'content' in cols, 'content column missing!'
print('Schema OK')
"
```

Expected: `Columns: ['id', 'title', 'url', 'source', 'published', 'category', 'content', 'scraped_at']` and `Schema OK`

**Step 3: Verify Flask API endpoints**

```bash
cd /home/algolinux2/Documents/GitHub/News_scraper && source venv/bin/activate && python -c "
from dashboard.app import app
with app.test_client() as c:
    for route in ['/api/news', '/api/news/grouped', '/api/news/live', '/api/status']:
        r = c.get(route)
        print(route, r.status_code)
"
```

Expected: All routes return `200`

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final integration smoke test passed"
```

---

## Summary of Files Created/Modified

| File | Action |
|---|---|
| `requirements.txt` | MODIFY — pin versions, add lxml + python-dotenv |
| `.env.example` | CREATE |
| `config.py` | MODIFY — dotenv, liveblog + resilience settings |
| `utils/__init__.py` | CREATE — empty |
| `utils/http.py` | CREATE — retry-capable HTTP helper |
| `scrapers/liveblog.py` | CREATE — AJ GraphQL liveblog scraper |
| `scrapers/liveblog_discovery.py` | CREATE — homepage + ticker auto-discovery |
| `scrapers/__init__.py` | MODIFY — export new scrapers |
| `storage/db.py` | MODIFY — thread safety, content column, liveblogs query |
| `main.py` | MODIFY — dual poll loops |
| `dashboard/app.py` | MODIFY — /api/news/live + /api/status |
| `dashboard/templates/index.html` | MODIFY — 3-col layout, LIVE section, filter bar |
| `README.md` | CREATE |
