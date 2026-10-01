"""
Generic RSS scraper for the FDE Briefing sources listed in config.FDE_RSS_FEEDS.

All of DoD, Defense News, Breaking Defense, The War Zone, Long War Journal,
Atlantic Council and RAND publish plain RSS/Atom, so one feedparser-based
loop covers all of them — no per-source module needed.
"""

import logging
from datetime import datetime

import feedparser
from bs4 import BeautifulSoup

from config import FDE_RSS_FEEDS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _parse_feed(source: str, category: str, url: str) -> list:
    """Parse a single feed and return a list of article dicts."""
    articles = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        if feed.bozo and not feed.entries:
            logger.warning("FDE feed [%s] failed: %s", source, feed.bozo_exception)
            return articles

        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue

            published = ""
            if getattr(entry, "published_parsed", None):
                try:
                    published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    published = entry.get("published", "")
            else:
                published = entry.get("published", "") or entry.get("updated", "")

            raw_desc = entry.get("summary", "") or entry.get("description", "") or ""
            content = BeautifulSoup(raw_desc, "html.parser").get_text(strip=True)

            articles.append({
                "title": title,
                "url": link,
                "source": source,
                "published": published,
                "category": category,
                "content": content,
            })

    except Exception as e:
        logger.error("FDE feed error [%s]: %s", source, e)

    return articles


def scrape_all() -> list:
    """Scrape every configured FDE RSS feed. Returns a deduplicated list."""
    seen_urls: set = set()
    all_articles: list = []

    for feed_info in FDE_RSS_FEEDS:
        for article in _parse_feed(feed_info["source"], feed_info["category"], feed_info["url"]):
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                all_articles.append(article)

    logger.info("FDE RSS: %d unique articles across %d feeds", len(all_articles), len(FDE_RSS_FEEDS))
    return all_articles
