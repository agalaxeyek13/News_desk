"""
Economic Times news scraper — fetches headlines via RSS feeds.

Uses feedparser with a browser User-Agent (ET's CDN returns HTTP 403 to
the default Python feedparser UA). Deduplicates across feeds using the
msid extracted from each article URL, so the same story appearing in
multiple feeds (e.g. markets + stocks + top_stories) is only returned once.
"""

import re
import logging
from datetime import datetime

import feedparser
from bs4 import BeautifulSoup

from config import ET_FEEDS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_MSID_RE = re.compile(r"/articleshow/(\d+)\.cms")


def get_msid(url: str):
    """Extract the numeric msid from an ET article URL, or return None."""
    m = _MSID_RE.search(url or "")
    return m.group(1) if m else None


def _parse_feed(category: str, url: str) -> list:
    """Parse a single ET RSS feed and return a list of article dicts."""
    articles = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        status = getattr(feed, "status", 200)
        if status != 200:
            logger.warning("ET feed [%s] returned HTTP %s", category, status)
            return articles

        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue

            msid = get_msid(link)
            article_id = f"ET_{msid}" if msid else link

            # Parse published date from struct_time or raw string
            published = ""
            if getattr(entry, "published_parsed", None):
                try:
                    published = datetime(
                        *entry.published_parsed[:6]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    published = entry.get("published", "")
            else:
                published = entry.get("published", "")

            # ET RSS description contains HTML: <a href...><img ...>text</a>
            # Extract plain-text summary and thumbnail src from it.
            raw_desc = entry.get("summary", "") or ""
            soup = BeautifulSoup(raw_desc, "html.parser")
            content = soup.get_text(strip=True)
            img = soup.find("img")
            thumbnail = img.get("src", "") if img else ""

            articles.append(
                {
                    "title": title,
                    "url": link,
                    "source": "Economic Times",
                    "published": published,
                    "category": category,
                    "content": content,
                    "msid": msid or "",
                    "thumbnail": thumbnail,
                    "article_id": article_id,
                }
            )

    except Exception as e:
        logger.error("ET feed error [%s]: %s", category, e)

    return articles


def scrape_et() -> list:
    """
    Scrape all configured ET RSS feeds.

    Deduplicates within the scraper by msid so cross-feed duplicates
    are collapsed before hitting the database.  Storage-level dedup
    (is_new / mark_seen) still applies on top of this.

    Returns list[dict], one dict per unique article.
    """
    seen_msids: set = set()
    seen_urls: set = set()
    all_articles: list = []

    for category, url in ET_FEEDS.items():
        for article in _parse_feed(category, url):
            msid = article.get("msid")
            if msid:
                if msid in seen_msids:
                    continue
                seen_msids.add(msid)
            else:
                if article["url"] in seen_urls:
                    continue
                seen_urls.add(article["url"])
            all_articles.append(article)

    logger.info(
        "Economic Times: %d unique articles across %d feeds",
        len(all_articles),
        len(ET_FEEDS),
    )
    return all_articles
