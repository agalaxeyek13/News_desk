"""
Al Jazeera GraphQL liveblog scraper.

Polls the AJ GraphQL API for liveblog updates every 15s (called from main.py fast loop).
Uses three operations:
  - SingleLiveBlogChildrensQuery  -> get all update post IDs for a liveblog slug
  - LiveBlogUpdateQuery           -> fetch full content of a single update by post ID
  - ArchipelagoSingleLiveBlogQuery -> get liveblog metadata (date, slug)
"""

import time
import logging
import json
from bs4 import BeautifulSoup

from config import ALJAZEERA_GRAPHQL_URL, REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_BACKOFF_SECONDS
from utils.http import get_with_retry

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.aljazeera.com/",
}

# Module-level set of seen post IDs per slug: { slug: set(post_ids) }
_seen_post_ids: dict = {}


def _gql(operation_name: str, variables: dict):
    """Call the AJ GraphQL endpoint and return parsed JSON, or None on error."""
    url = (
        f"{ALJAZEERA_GRAPHQL_URL}"
        f"?wp-site=aje"
        f"&operationName={operation_name}"
        f"&variables={json.dumps(variables, separators=(',', ':'))}"
        f"&extensions={{}}"
    )
    try:
        resp = get_with_retry(
            url, HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
            backoff=RETRY_BACKOFF_SECONDS,
        )
        return resp.json()
    except Exception as e:
        logger.error("GraphQL %s failed: %s", operation_name, e)
        return None


def _get_children_ids(slug: str) -> list:
    """Return list of post IDs for all updates in a liveblog."""
    data = _gql("SingleLiveBlogChildrensQuery", {"postName": slug})
    if not data:
        return []
    try:
        nodes = data["data"]["post"]["children"]["nodes"]
        return [node["databaseId"] for node in nodes if "databaseId" in node]
    except (KeyError, TypeError) as e:
        logger.debug("Could not parse children for %s: %s", slug, e)
        return []


def _get_liveblog_meta(slug: str) -> dict:
    """Return {'year': str, 'month': str, 'day': str} for URL construction."""
    data = _gql("ArchipelagoSingleLiveBlogQuery", {
        "name": slug,
        "postType": "liveblog",
        "preview": "",
    })
    meta = {"year": "2025", "month": "01", "day": "01"}
    if not data:
        return meta
    try:
        post = data["data"]["post"]
        date_str = post.get("date", "")  # e.g. "2025-10-12T14:30:00"
        if date_str and "T" in date_str:
            parts = date_str.split("T")[0].split("-")
            meta["year"], meta["month"], meta["day"] = parts[0], parts[1], parts[2]
    except (KeyError, TypeError):
        pass
    return meta


def _get_update(post_id: int):
    """Fetch full content of a single liveblog update."""
    data = _gql("LiveBlogUpdateQuery", {
        "postID": post_id,
        "postType": "liveblog-update",
        "preview": "",
        "isAmp": False,
    })
    if not data:
        return None
    try:
        post = data["data"]["post"]
        title = post.get("title", "").strip()
        published = post.get("date", "")
        if published and "T" in published:
            published = published.replace("T", " ")[:19]

        # Strip HTML from content
        raw_html = post.get("content", "") or ""
        content = BeautifulSoup(raw_html, "lxml").get_text(separator=" ", strip=True)

        return {
            "title": title,
            "content": content,
            "published": published,
        }
    except (KeyError, TypeError) as e:
        logger.debug("Could not parse update %d: %s", post_id, e)
        return None


def scrape(slug: str) -> list:
    """
    Fetch new liveblog updates for a given slug.
    Only returns updates not yet seen (tracked in module-level _seen_post_ids).

    Returns list of article dicts: {title, url, source, published, category, content}
    """
    if slug not in _seen_post_ids:
        _seen_post_ids[slug] = set()

    post_ids = _get_children_ids(slug)
    if not post_ids:
        return []

    new_ids = [pid for pid in post_ids if pid not in _seen_post_ids[slug]]
    if not new_ids:
        return []

    # Get liveblog meta once for URL construction
    meta = _get_liveblog_meta(slug)

    articles = []
    for post_id in new_ids:
        update = _get_update(post_id)
        if update and update.get("title"):
            url = (
                f"https://www.aljazeera.com/news/liveblog/"
                f"{meta['year']}/{meta['month']}/{meta['day']}"
                f"/{slug}?update={post_id}"
            )
            articles.append({
                "title": update["title"],
                "url": url,
                "source": "Al Jazeera",
                "published": update["published"],
                "category": "🔴 LIVE",
                "content": update["content"],
            })
        _seen_post_ids[slug].add(post_id)
        time.sleep(0.3)  # Rate limiting between individual update fetches

    if articles:
        logger.info("Liveblog [%s]: %d new updates", slug, len(articles))
    return articles


def reset_seen(slug=None):
    """Reset seen state. Used in tests. If slug is None, resets all."""
    global _seen_post_ids
    if slug is None:
        _seen_post_ids = {}
    elif slug in _seen_post_ids:
        del _seen_post_ids[slug]
