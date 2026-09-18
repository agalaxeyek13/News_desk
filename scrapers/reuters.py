"""
Reuters news scraper — fetches headlines via Google News RSS (site:reuters.com).
Direct scraping of reuters.com returns 401, so we use Google News as a proxy.
Uses multiple category-specific queries to capture ALL types of news.
"""

import feedparser
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Multiple queries to cover all Reuters categories
REUTERS_FEEDS = [
    {
        "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "category": "Top News",
    },
    {
        "url": "https://news.google.com/rss/search?q=site:reuters.com+business+OR+economy+OR+markets&hl=en-US&gl=US&ceid=US:en",
        "category": "Business",
    },
    {
        "url": "https://news.google.com/rss/search?q=site:reuters.com+technology+OR+AI+OR+tech&hl=en-US&gl=US&ceid=US:en",
        "category": "Technology",
    },
    {
        "url": "https://news.google.com/rss/search?q=site:reuters.com+sports+OR+football+OR+cricket&hl=en-US&gl=US&ceid=US:en",
        "category": "Sports",
    },
    {
        "url": "https://news.google.com/rss/search?q=site:reuters.com+health+OR+science&hl=en-US&gl=US&ceid=US:en",
        "category": "Health & Science",
    },
    {
        "url": "https://news.google.com/rss/search?q=site:reuters.com+entertainment+OR+lifestyle&hl=en-US&gl=US&ceid=US:en",
        "category": "Entertainment",
    },
]


def _clean_title(raw_title):
    """Remove trailing ' - Reuters' from Google News titles."""
    return re.sub(r"\s*-\s*Reuters\s*$", "", raw_title).strip()


def _parse_feed(feed_url, category):
    """Parse a single Google News RSS feed for Reuters articles."""
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            return articles

        for entry in feed.entries:
            raw_title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not raw_title or not link:
                continue

            # Only include Reuters articles
            source_tag = entry.get("source", {})
            source_name = ""
            if hasattr(source_tag, "get"):
                source_name = source_tag.get("value", "")
            elif isinstance(source_tag, str):
                source_name = source_tag
            
            title = _clean_title(raw_title)

            # Parse published date
            published = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    published = entry.get("published", "")
            elif entry.get("published"):
                published = entry.get("published", "")

            articles.append({
                "title": title,
                "url": link,
                "source": "Reuters",
                "published": published,
                "category": category,
            })

    except Exception as e:
        logger.error("Reuters feed parse error (%s): %s", category, e)

    return articles


def scrape():
    """
    Fetch Reuters articles via multiple Google News RSS queries.
    Returns a list of article dicts, deduplicated by URL.
    """
    all_articles = []
    seen_urls = set()

    for feed_info in REUTERS_FEEDS:
        articles = _parse_feed(feed_info["url"], feed_info["category"])
        for article in articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                all_articles.append(article)

    logger.info("Reuters: fetched %d unique articles across %d feeds", len(all_articles), len(REUTERS_FEEDS))
    return all_articles
