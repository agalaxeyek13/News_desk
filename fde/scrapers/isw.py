"""
Institute for the Study of War — "Iran Update" scraper.

ISW publishes no RSS for this product line. The listing page only gives
title + link, so this also fetches each article's own page for its real
body text (div.dynamic-entry-content) — without that, extraction/linking
would have nothing but a dated headline ("Iran Update, September 17,
2026") to work with, which carries no usable entities.
"""

import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from config import FDE_ISW_LISTING_URL

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_MAX_CONTENT_CHARS = 4000


def _parse_published(title: str) -> str:
    """Parse 'Iran Update, September 10, 2026' -> '2026-09-10 00:00:00'."""
    try:
        date_part = title.split(",", 1)[1].strip()
        dt = datetime.strptime(date_part, "%B %d, %Y")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _fetch_body(url: str) -> str:
    """Fetch one Iran Update article page and return its body text."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        div = soup.find("div", class_="dynamic-entry-content")
        if not div:
            return ""
        return div.get_text(" ", strip=True)[:_MAX_CONTENT_CHARS]
    except Exception as e:
        logger.warning("ISW article fetch failed [%s]: %s", url, e)
        return ""


def scrape() -> list:
    """Scrape the ISW Iran Update listing page, then each entry's full body text."""
    articles = []
    try:
        resp = requests.get(FDE_ISW_LISTING_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for h3 in soup.select("h3.research-card-title"):
            a_tag = h3.find("a", href=True)
            if not a_tag:
                continue
            url = a_tag["href"].strip()
            title = a_tag.get_text(strip=True)
            if not url or not title or "iran-update" not in url:
                continue

            articles.append({
                "title": title,
                "url": url,
                "source": "ISW Iran Update",
                "published": _parse_published(title),
                "category": "Analysis",
                "content": "",
            })

        logger.info("ISW Iran Update: %d entries found, fetching bodies", len(articles))

        for article in articles:
            article["content"] = _fetch_body(article["url"])

    except Exception as e:
        logger.error("ISW Iran Update scrape error: %s", e)

    return articles
