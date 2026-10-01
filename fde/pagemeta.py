"""
Publish time and thumbnail read from an article's own page.

Feeds and listing pages don't always carry a real timestamp — Al Jazeera's
homepage gives none, ISW's listing only has a date in the title — so the
page's own metadata is the source of truth for "when was this published".
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

PUBLISHED_FORMAT = "%Y-%m-%d %H:%M:%S"

_META_PUBLISHED = (
    {"property": "article:published_time"},
    {"name": "publishedDate"},
    {"itemprop": "datePublished"},
    {"name": "date"},
)
_JSONLD_PUBLISHED_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_URL_DATE_RE = re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/")


def to_utc_string(value: str) -> str:
    """ISO-8601 (with or without offset / 'Z') -> 'YYYY-MM-DD HH:MM:SS' UTC.
    A value without an offset is taken as UTC. Returns '' if unparseable."""
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime(PUBLISHED_FORMAT)


def date_from_url(url: str) -> str:
    """'/2026/10/1/' in a URL -> '2026-10-01 00:00:00', else ''."""
    match = _URL_DATE_RE.search(url or "")
    if not match:
        return ""
    try:
        return datetime(*map(int, match.groups())).strftime(PUBLISHED_FORMAT)
    except ValueError:
        return ""


def extract_published(soup: BeautifulSoup, html: str) -> str:
    for attrs in _META_PUBLISHED:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            published = to_utc_string(tag["content"])
            if published:
                return published
    match = _JSONLD_PUBLISHED_RE.search(html)
    return to_utc_string(match.group(1)) if match else ""


def extract_thumbnail(soup: BeautifulSoup) -> str:
    for prop in ("og:image", "twitter:image"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def fetch_page(url: str, timeout: int = 15):
    """GET a page and return (soup, html), or (None, '') on any failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser"), resp.text
    except Exception as e:
        logger.debug("Page fetch failed [%s]: %s", url, e)
        return None, ""


def fill_page_meta(article: dict) -> dict:
    """Fill a missing `published` and `thumbnail` from the article's own page."""
    if article.get("published") and article.get("thumbnail"):
        return article
    if "news.google.com" in article.get("url", ""):
        return article  # a JS redirect page — nothing useful to read
    soup, html = fetch_page(article["url"])
    if soup is not None:
        if not article.get("published"):
            article["published"] = extract_published(soup, html)
        if not article.get("thumbnail"):
            article["thumbnail"] = extract_thumbnail(soup)
    return article


def fill_page_meta_all(articles: list, workers: int = 12) -> list:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fill_page_meta, articles))
    return articles
