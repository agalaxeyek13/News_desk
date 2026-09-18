"""
Auto-discovers active Al Jazeera liveblogs from:
1. AJ homepage HTML (links matching /liveblog/YYYY/MM/DD/SLUG)
2. GraphQL ArchipelagoBreakingTickerQuery (breaking/live news ticker)
"""

import re
import logging
import json

from bs4 import BeautifulSoup

from config import ALJAZEERA_GRAPHQL_URL, REQUEST_TIMEOUT_SECONDS
from utils.http import get_with_retry

logger = logging.getLogger(__name__)

ALJAZEERA_HOME_URL = "https://www.aljazeera.com/"
LIVEBLOG_SLUG_RE = re.compile(r"/liveblog/\d{4}/\d{2}/\d{2}/([^/?#]+)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.aljazeera.com/",
}

GQL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.aljazeera.com/",
}


def _slugs_from_homepage() -> set:
    """Scrape AJ homepage HTML and extract liveblog slugs from URLs."""
    slugs = set()
    try:
        resp = get_with_retry(ALJAZEERA_HOME_URL, HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            m = LIVEBLOG_SLUG_RE.search(href)
            if m:
                slugs.add(m.group(1))
        logger.info("Discovery (HTML): found %d liveblog slugs", len(slugs))
    except Exception as e:
        logger.error("Homepage discovery failed: %s", e)
    return slugs


def _slugs_from_breaking_ticker() -> set:
    """Query AJ GraphQL breaking ticker for any live items."""
    slugs = set()
    url = (
        f"{ALJAZEERA_GRAPHQL_URL}"
        f"?wp-site=aje"
        f"&operationName=ArchipelagoBreakingTickerQuery"
        f"&variables={{}}"
        f"&extensions={{}}"
    )
    try:
        resp = get_with_retry(url, GQL_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        data = resp.json()
        nodes = data.get("data", {}).get("breakingTicker", {}).get("nodes", [])
        for node in nodes:
            uri = node.get("uri", "")
            m = LIVEBLOG_SLUG_RE.search(uri)
            if m:
                slugs.add(m.group(1))
        logger.info("Discovery (ticker): found %d liveblog slugs", len(slugs))
    except Exception as e:
        logger.error("Breaking ticker discovery failed: %s", e)
    return slugs


def discover() -> list:
    """
    Discover all currently active liveblog slugs.
    Merges results from homepage HTML and breaking ticker.
    Returns a sorted list of unique slugs.
    """
    slugs = _slugs_from_homepage() | _slugs_from_breaking_ticker()
    return sorted(slugs)
