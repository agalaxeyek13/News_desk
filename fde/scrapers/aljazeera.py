"""
Al Jazeera for the FDE Briefing, with real publish times.

The shared dashboard scraper (scrapers/aljazeera.py) stamps every homepage
headline with the scrape time, which is fine for a live ticker but makes a
months-old opinion piece look like today's news in a "last 24 hours"
briefing. Here RSS (real timestamps) wins, and homepage-only links get
their publish time from the article page itself.
"""

import logging

from scrapers import aljazeera
from fde.pagemeta import date_from_url, fill_page_meta_all

logger = logging.getLogger(__name__)


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def scrape() -> list:
    articles = []
    seen = set()

    for article in aljazeera._scrape_rss():
        article["url"] = _strip_query(article["url"])
        if article["url"] not in seen:
            seen.add(article["url"])
            articles.append(article)

    homepage_only = []
    for article in aljazeera._scrape_html():
        article["url"] = _strip_query(article["url"])
        if article["url"] in seen:
            continue
        seen.add(article["url"])
        article["published"] = ""
        homepage_only.append(article)

    fill_page_meta_all(homepage_only)

    resolved = 0
    for article in homepage_only:
        if not article["published"] and "/liveblog/" in article["url"]:
            # Liveblog pages carry no publish meta; the URL holds the day it opened.
            article["published"] = date_from_url(article["url"])
            article["live"] = True
        if article["published"]:
            resolved += 1
            articles.append(article)

    logger.info(
        "Al Jazeera (FDE): %d articles (%d homepage-only, %d with a resolved publish time)",
        len(articles), len(homepage_only), resolved,
    )
    return articles
