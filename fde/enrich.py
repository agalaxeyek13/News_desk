"""
Fetches the real article page for every article that survives the
filter gate, instead of relying on the RSS teaser blurb.

RSS descriptions are often just 1-2 sentences — not enough for a real
synthesis paragraph. This runs only on the small filtered set (recent +
relevant, typically a couple dozen articles), not the full scrape, so
the extra requests are bounded. Also picks up each page's og:image for
use as a thumbnail in the email.
"""

import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_MIN_CHARS_TO_SKIP = 300  # already has enough text — don't bother re-fetching
_MAX_CHARS = 4000

# Already fetches its own full body at scrape time.
_SKIP_SOURCES = {"ISW Iran Update"}


def _extract_body(soup: BeautifulSoup) -> str:
    """Best-effort article body extraction: <article>, else the densest
    paragraph container, else all <p> tags on the page."""
    article_tag = soup.find("article")
    if article_tag:
        text = article_tag.get_text(" ", strip=True)
        if len(text) > 200:
            return text

    paragraphs = soup.find_all("p")
    return " ".join(p.get_text(" ", strip=True) for p in paragraphs)


def _extract_thumbnail(soup: BeautifulSoup) -> str:
    for prop in ("og:image", "twitter:image"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def enrich_article(article: dict) -> dict:
    """Fetch the real article page and fill in content/thumbnail if useful."""
    if article.get("source") in _SKIP_SOURCES:
        return article
    if len(article.get("content", "")) >= _MIN_CHARS_TO_SKIP and article.get("thumbnail"):
        return article

    try:
        resp = requests.get(article["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        body = _extract_body(soup)
        if len(body) > len(article.get("content", "")):
            article["content"] = body[:_MAX_CHARS]

        if not article.get("thumbnail"):
            thumb = _extract_thumbnail(soup)
            if thumb:
                article["thumbnail"] = thumb

    except Exception as e:
        logger.debug("Enrichment fetch failed [%s]: %s", article.get("url"), e)

    return article


def enrich_articles(articles: list) -> list:
    for article in articles:
        enrich_article(article)
    logger.info(
        "Enrichment: fetched full text for %d articles (%d already had a thumbnail)",
        sum(1 for a in articles if a.get("source") not in _SKIP_SOURCES),
        sum(1 for a in articles if a.get("thumbnail")),
    )
    return articles
