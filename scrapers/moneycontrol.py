"""
MoneyControl news scraper — fetches headlines via RSS feeds + HTML scraping,
and live market blog updates via Schema.org LiveBlogPosting JSON-LD.

Primary: 6 confirmed RSS feeds (latestnews, MCtopnews, buzzingstocks,
         economy, business, commodities).
Backup:  HTML scrape of /news/news-all/ for articles not yet in RSS.
Live:    Schema.org LiveBlogPosting JSON-LD from today's market live blog.
         Discovered automatically from /news/tags/live-blog.html every poll.

No authentication required. All endpoints are publicly accessible.
"""

import re
import json
import logging
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from config import MC_RSS_FEEDS as _MC_RSS_FEEDS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
    "Accept-Language": "en-US,en;q=0.5",
}

MC_NEWS_ALL_URL = "https://www.moneycontrol.com/news/news-all/"
MC_LIVE_TAGS_URL = "https://www.moneycontrol.com/news/tags/live-blog.html"

# Matches MC liveblog article URLs ending in -liveblog-{ID}.html
_LIVEBLOG_RE = re.compile(r"https://www\.moneycontrol\.com/.+-liveblog-\d+\.html")

# Valid article URL pattern
_ARTICLE_RE = re.compile(
    r"https://www\.moneycontrol\.com/news/.+/[a-z0-9-]+-\d+\.html"
)


def _scrape_rss() -> list:
    """Fetch articles from all MoneyControl RSS feeds."""
    articles = []
    seen_urls: set = set()

    for feed_info in _MC_RSS_FEEDS:
        try:
            feed = feedparser.parse(
                feed_info["url"],
                request_headers={"User-Agent": HEADERS["User-Agent"]},
            )
            if feed.bozo and not feed.entries:
                logger.warning("MC RSS feed failed: %s", feed_info["url"])
                continue

            for entry in feed.entries:
                title = (entry.get("title") or "").strip()
                link = (entry.get("link") or "").strip()
                if not title or not link or link in seen_urls:
                    continue
                seen_urls.add(link)

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

                raw_desc = entry.get("summary", "") or entry.get("description", "") or ""
                content = BeautifulSoup(raw_desc, "lxml").get_text(strip=True)

                articles.append(
                    {
                        "title": title,
                        "url": link,
                        "source": "MoneyControl",
                        "published": published,
                        "category": f"📊 {feed_info['category']}",
                        "content": content,
                    }
                )

            logger.info(
                "MC RSS [%s]: %d articles", feed_info["category"], len(feed.entries)
            )

        except Exception as e:
            logger.error("MC RSS error [%s]: %s", feed_info["url"], e)

    return articles


def _scrape_html() -> list:
    """
    Scrape the MC news-all listing page for the latest article links.
    Articles appear in <li class="clearfix"> elements.
    URL pattern: moneycontrol.com/news/{category}/{slug}-{id}.html
    """
    articles = []
    try:
        resp = requests.get(MC_NEWS_ALL_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        seen_urls: set = set()

        for li in soup.find_all("li", class_="clearfix"):
            link_tag = li.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"].strip()
            if not _ARTICLE_RE.match(href) or href in seen_urls:
                continue
            seen_urls.add(href)

            title = link_tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            articles.append(
                {
                    "title": title,
                    "url": href,
                    "source": "MoneyControl",
                    "published": now_str,
                    "category": "📊 Latest",
                    "content": "",
                }
            )

        logger.info("MC HTML scrape: %d articles", len(articles))

    except Exception as e:
        logger.error("MC HTML scrape error: %s", e)

    return articles


def scrape() -> list:
    """
    Scrape MoneyControl from RSS feeds (primary) + HTML listing (backup).
    Returns a deduplicated list of article dicts.
    """
    seen_urls: set = set()
    all_articles: list = []

    # RSS first — has proper timestamps and summaries
    for article in _scrape_rss():
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    # HTML listing — catches articles not yet in RSS
    for article in _scrape_html():
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    logger.info("MoneyControl total: %d unique articles", len(all_articles))
    return all_articles


def _discover_live_blog_url() -> str | None:
    """Fetch the MC live-blog tags page and return the most recent liveblog URL."""
    try:
        resp = requests.get(MC_LIVE_TAGS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if _LIVEBLOG_RE.match(href):
                return href
    except Exception as e:
        logger.error("MC live blog discovery error: %s", e)
    return None


def scrape_live() -> list:
    """
    Scrape today's MoneyControl market live blog.

    Discovers the current live blog URL from the tags page, then extracts all
    updates from the Schema.org LiveBlogPosting JSON-LD embedded in the page.
    Each update becomes an article with source='MoneyControl' and
    category='📊 Live Markets' (normCat sees 'live' → red Live tag).

    Returns a list of article dicts compatible with mark_seen().
    """
    lb_url = _discover_live_blog_url()
    if not lb_url:
        logger.warning("MC live blog: no liveblog URL discovered")
        return []

    try:
        resp = requests.get(lb_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(data, dict) or data.get("@type") != "LiveBlogPosting":
                continue

            articles = []
            for update in data.get("liveBlogUpdate", []):
                title = (update.get("headline") or "").strip()
                url = (update.get("url") or "").strip()
                if not title or not url:
                    continue

                published = ""
                raw_dt = update.get("datePublished") or update.get("dateModified") or ""
                if raw_dt:
                    try:
                        dt = datetime.fromisoformat(raw_dt)
                        published = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        published = raw_dt

                body = (update.get("articleBody") or "").strip()

                articles.append({
                    "title": title,
                    "url": url,
                    "source": "MoneyControl",
                    "published": published,
                    "category": "📊 Live Markets",
                    "content": body[:500] if body else "",
                })

            logger.info("MC live blog: %d updates from %s", len(articles), lb_url)
            return articles

    except Exception as e:
        logger.error("MC live blog scrape error: %s", e)

    return []
