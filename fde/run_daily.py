#!/usr/bin/env python3
"""
FDE Briefing — daily entry point.

Run once a day (Windows Task Scheduler / cron), not as a long-lived
process: scrape -> filter -> cluster -> score -> compose -> send.

    python -m fde.run_daily
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fde.run_daily")

from scrapers import aljazeera, reuters
from fde.scrapers import rss as fde_rss, isw as fde_isw
from fde.filter import filter_articles
from fde.enrich import enrich_articles
from fde.linker import build_clusters
from fde.scorer import score_clusters
from fde.composer import compose_email
from fde.mailer import send_briefing
from fde.store import init_fde_db, filter_unsent, mark_articles_sent
from config import FDE_RECENCY_HOURS


def gather_articles() -> list:
    """Scrape every FDE source and return the combined, deduplicated list."""
    all_articles = []

    for name, fn in [
        ("Al Jazeera", aljazeera.scrape),
        ("Reuters", reuters.scrape),
        ("FDE RSS sources", fde_rss.scrape_all),
        ("ISW Iran Update", fde_isw.scrape),
    ]:
        try:
            all_articles.extend(fn())
        except Exception as e:
            logger.error("%s scrape failed: %s", name, e)

    seen_urls = set()
    deduped = []
    for article in all_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            deduped.append(article)

    logger.info("Gathered %d unique articles across all sources", len(deduped))
    return deduped


def main():
    init_fde_db()

    articles = gather_articles()
    relevant = filter_articles(articles)
    logger.info("%d of %d articles passed the %dh recency + US-Iran relevance gate", len(relevant), len(articles), FDE_RECENCY_HOURS)

    unsent = filter_unsent(relevant)
    logger.info("%d of %d already appeared in a past briefing — %d new", len(relevant) - len(unsent), len(relevant), len(unsent))

    if not unsent:
        logger.warning("No new relevant articles today — skipping send")
        return

    unsent = enrich_articles(unsent)
    clusters = build_clusters(unsent)
    clusters = score_clusters(clusters)

    subject, html = compose_email(clusters)
    logger.info("Composed briefing: %s", subject)

    sent = send_briefing(subject, html)
    if not sent:
        logger.error("Briefing was composed but NOT sent — check mail configuration")
        return

    all_briefed = [a for c in clusters for a in c["articles"]]
    mark_articles_sent(all_briefed)
    logger.info("Marked %d articles as briefed", len(all_briefed))


if __name__ == "__main__":
    main()
