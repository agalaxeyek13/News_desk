"""
Al Jazeera news scraper — fetches headlines via RSS feed + direct HTML scrape.
HTML scraping catches the absolute latest / breaking / live updates that
may not yet appear in the RSS feed.
"""

import feedparser
import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ALJAZEERA_RSS_URL = "https://www.aljazeera.com/xml/rss/all.xml"
ALJAZEERA_HOME_URL = "https://www.aljazeera.com/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# URL patterns for valid Al Jazeera articles
VALID_PATHS = re.compile(r"^/(news|features|economy|opinions|sports|program|video|podcasts|gallery|liveblog|tag)/")


def _scrape_rss():
    """Fetch articles from Al Jazeera RSS feed."""
    articles = []
    try:
        feed = feedparser.parse(ALJAZEERA_RSS_URL)
        if feed.bozo and not feed.entries:
            logger.warning("Al Jazeera RSS feed error: %s", feed.bozo_exception)
            return articles

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            published = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    published = entry.get("published", "")
            elif entry.get("published"):
                published = entry.get("published", "")

            categories = []
            if hasattr(entry, "tags"):
                categories = [t.get("term", "") for t in entry.tags if t.get("term")]
            category = ", ".join(categories) if categories else "General"

            articles.append({
                "title": title,
                "url": link,
                "source": "Al Jazeera",
                "published": published,
                "category": category,
            })

        logger.info("  RSS: %d articles", len(articles))

    except Exception as e:
        logger.error("Al Jazeera RSS error: %s", e)

    return articles


def _scrape_html():
    """Scrape the Al Jazeera homepage for the absolute latest headlines."""
    articles = []
    try:
        resp = requests.get(ALJAZEERA_HOME_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        seen_urls = set()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Grab ALL links on the page that point to articles
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()

            # Match both absolute and relative AJ article URLs
            path = href
            if href.startswith("https://www.aljazeera.com/"):
                path = href.replace("https://www.aljazeera.com", "")
            elif not href.startswith("/"):
                continue

            if not VALID_PATHS.match(path):
                continue

            url = "https://www.aljazeera.com" + path if path.startswith("/") else href

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract title from nested heading or span, fallback to link text
            title = ""
            heading = a_tag.find(["h1", "h2", "h3", "h4", "h5", "span"])
            if heading:
                title = heading.get_text(strip=True)
            if not title:
                title = a_tag.get_text(strip=True)

            if not title or len(title) < 10:
                continue

            # Categorize from URL
            category = "News"
            if "/liveblog/" in path:
                category = "🔴 LIVE"
            elif "/features/" in path:
                category = "Features"
            elif "/economy/" in path:
                category = "Economy"
            elif "/opinions/" in path:
                category = "Opinion"
            elif "/sports/" in path:
                category = "Sports"
            elif "/video/" in path:
                category = "Video"

            articles.append({
                "title": title,
                "url": url,
                "source": "Al Jazeera",
                "published": now_str,
                "category": category,
            })

        logger.info("  HTML: %d headlines from homepage", len(articles))

    except Exception as e:
        logger.error("Al Jazeera HTML scrape error: %s", e)

    return articles


def scrape():
    """
    Fetch Al Jazeera articles from both RSS and HTML scraping.
    Returns deduplicated list with the freshest data.
    """
    seen_urls = set()
    all_articles = []

    # HTML scraping first (most current from the homepage)
    html_articles = _scrape_html()
    for article in html_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    # RSS feed (has proper timestamps)
    rss_articles = _scrape_rss()
    for article in rss_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    logger.info("Al Jazeera total: %d unique articles", len(all_articles))
    return all_articles
