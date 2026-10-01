#!/usr/bin/env python3
"""
FDE Briefing — daily entry point.

Run once a day (Windows Task Scheduler / cron), not as a long-lived
process: scrape -> filter -> cluster -> score -> compose -> send.

    python -m fde.run_daily              # compose and send
    python -m fde.run_daily --dry-run    # compose only, write briefing_preview.html
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fde.run_daily")

from scrapers import reuters
from fde.scrapers import rss as fde_rss, isw as fde_isw, aljazeera as fde_aljazeera
from fde.filter import filter_recent, is_relevant, is_opinion
from fde.enrich import enrich_articles
from fde.pagemeta import fill_page_meta_all
from fde.linker import build_clusters
from fde.scorer import score_clusters
from fde.composer import compose_email
from fde.mailer import send_briefing
from fde.store import init_fde_db, filter_unsent, mark_articles_sent
from config import FDE_RECENCY_HOURS, FDE_GENERAL_NEWS_SOURCES

PREVIEW_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "briefing_preview.html")


def gather_articles() -> list:
    """Scrape every FDE source and return the combined, deduplicated list."""
    all_articles = []

    for name, fn in [
        ("Al Jazeera", fde_aljazeera.scrape),
        ("Reuters", reuters.scrape),
        ("FDE RSS sources", fde_rss.scrape_all),
        ("ISW Iran Update", fde_isw.scrape),
    ]:
        try:
            all_articles.extend(fn())
        except Exception as e:
            logger.error("%s scrape failed: %s", name, e)

    # Same URL, or the same headline twice from one outlet (a liveblog
    # entry and the full article, say), is one item.
    seen_urls, seen_titles = set(), set()
    deduped = []
    for article in all_articles:
        title_key = (article["source"], article["title"].strip().lower())
        if article["url"] in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(article["url"])
        seen_titles.add(title_key)
        deduped.append(article)

    logger.info("Gathered %d unique articles across all sources", len(deduped))
    return deduped


def main(dry_run: bool = False):
    init_fde_db()

    recent = filter_unsent(filter_recent(gather_articles()))

    # Written sections: US-Iran news. Listed below them: everything else the
    # defense/regional outlets published in the window, the relevant items
    # from the general-news outlets, and opinion pieces.
    briefable = [a for a in recent if is_relevant(a) and not is_opinion(a)]
    briefable_urls = {a["url"] for a in briefable}
    listing = [
        a for a in recent
        if a["url"] not in briefable_urls
        and (a["source"] not in FDE_GENERAL_NEWS_SOURCES or is_relevant(a))
    ]
    logger.info(
        "Last %dh: %d new articles -> %d for written sections, %d listed",
        FDE_RECENCY_HOURS, len(recent), len(briefable), len(listing),
    )

    if not briefable and not listing:
        logger.warning("Nothing new in the last %dh — skipping send", FDE_RECENCY_HOURS)
        return

    enrich_articles(briefable)
    fill_page_meta_all(listing)
    clusters = score_clusters(build_clusters(briefable), save_history=not dry_run)

    subject, html = compose_email(clusters, listing)
    logger.info("Composed briefing: %s", subject)

    if dry_run:
        with open(PREVIEW_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Dry run — not sent. Preview written to %s", PREVIEW_PATH)
        return

    sent = send_briefing(subject, html)
    if not sent:
        logger.error("Briefing was composed but NOT sent — check mail configuration")
        return

    all_briefed = [a for c in clusters for a in c["articles"]] + listing
    mark_articles_sent(all_briefed)
    logger.info("Marked %d articles as briefed", len(all_briefed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compose and send the FDE Briefing.")
    parser.add_argument("--dry-run", action="store_true", help="compose only; write briefing_preview.html instead of sending")
    main(dry_run=parser.parse_args().dry_run)
