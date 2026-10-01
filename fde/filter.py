"""
Cheap gates applied before any LLM call: recency, then keyword relevance.

Al Jazeera, Reuters, and the defense trade press cover far more than
US-Iran, and their feeds often carry items far older than a day — this
drops both the irrelevant and the stale ones, so the (expensive)
entity-extraction step only runs on articles that could plausibly belong
in *today's* briefing.
"""

import logging
from datetime import datetime, timedelta

from config import FDE_KEYWORDS, FDE_RECENCY_HOURS

logger = logging.getLogger(__name__)

_PUBLISHED_FORMAT = "%Y-%m-%d %H:%M:%S"


def is_relevant(article: dict) -> bool:
    """True if the article's title or content mentions a US-Iran keyword."""
    text = f"{article.get('title', '')} {article.get('content', '')}".lower()
    return any(keyword in text for keyword in FDE_KEYWORDS)


def is_recent(article: dict, hours: int = FDE_RECENCY_HOURS) -> bool:
    """
    True if the article's `published` timestamp is within the last `hours`.
    An article with a missing or unparseable timestamp is kept rather than
    dropped — better to include an ambiguous one than silently lose it.
    """
    published = article.get("published", "")
    if not published:
        return True
    try:
        published_dt = datetime.strptime(published, _PUBLISHED_FORMAT)
    except ValueError:
        return True
    return published_dt >= datetime.utcnow() - timedelta(hours=hours)


def filter_articles(articles: list, hours: int = FDE_RECENCY_HOURS) -> list:
    """Return only articles that are both recent (last `hours`) and US-Iran relevant."""
    recent = [a for a in articles if is_recent(a, hours)]
    logger.info("Recency filter (%dh): %d of %d articles kept", hours, len(recent), len(articles))
    relevant = [a for a in recent if is_relevant(a)]
    return relevant
