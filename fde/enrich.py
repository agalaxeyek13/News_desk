"""
Fetches the real article page for every article that gets a written
section, instead of relying on the RSS teaser blurb.

RSS descriptions are often just 1-2 sentences — not enough for a real
synthesis paragraph. This runs only on the filtered set (recent +
relevant), not the full scrape, so the extra requests are bounded. Also
picks up each page's og:image for use as a thumbnail in the email.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from fde.pagemeta import fetch_page, extract_thumbnail, extract_published

logger = logging.getLogger(__name__)

_MIN_CHARS_TO_SKIP = 300  # already has enough text — don't bother re-fetching
_MAX_CHARS = 4000

# Already fetches its own full body at scrape time.
_SKIP_SOURCES = {"ISW Iran Update"}


def _extract_body(soup: BeautifulSoup) -> str:
    """Best-effort article body extraction: <article>, else all <p> tags on the page."""
    article_tag = soup.find("article")
    if article_tag:
        text = article_tag.get_text(" ", strip=True)
        if len(text) > 200:
            return text

    paragraphs = soup.find_all("p")
    return " ".join(p.get_text(" ", strip=True) for p in paragraphs)


def enrich_article(article: dict) -> dict:
    """Fetch the real article page and fill in content/thumbnail/published if useful."""
    if article.get("source") in _SKIP_SOURCES:
        return article
    if len(article.get("content", "")) >= _MIN_CHARS_TO_SKIP and article.get("thumbnail"):
        return article
    if "news.google.com" in article.get("url", ""):
        return article  # a JS redirect page — its only og:image is the Google News logo

    soup, html = fetch_page(article["url"])
    if soup is None:
        return article

    body = _extract_body(soup)
    if len(body) > len(article.get("content", "")):
        article["content"] = body[:_MAX_CHARS]
    if not article.get("thumbnail"):
        article["thumbnail"] = extract_thumbnail(soup)
    if not article.get("published"):
        article["published"] = extract_published(soup, html)
    return article


def enrich_articles(articles: list, workers: int = 12) -> list:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(enrich_article, articles))
    logger.info(
        "Enrichment: %d articles (%d now have a thumbnail)",
        len(articles), sum(1 for a in articles if a.get("thumbnail")),
    )
    return articles
