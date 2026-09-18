#!/usr/bin/env python3
"""
📰 News Alert System — Main Entry Point
Runs poll loops:
  - Slow loop:      RSS + HTML every POLL_INTERVAL_SECONDS (120s)
  - Fast loop:      GraphQL liveblogs every LIVEBLOG_POLL_INTERVAL_SECONDS (15s)
  - ET loop:        Economic Times RSS every ET_POLL_INTERVAL_SECONDS (60s)
  - MC loop:        MoneyControl RSS every MC_POLL_INTERVAL_SECONDS (60s)
  - MC live loop:   MoneyControl live blog every MC_LIVE_POLL_INTERVAL_SECONDS (30s)
  - ScanX loop:     News Flash every SCANX_POLL_INTERVAL_SECONDS (15s)
"""

import sys
import os
import time
import logging
import threading
import signal
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    POLL_INTERVAL_SECONDS,
    LIVEBLOG_POLL_INTERVAL_SECONDS,
    ENABLE_DESKTOP_NOTIFICATIONS,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    TRACKED_LIVEBLOG_SLUGS,
    ENABLE_LIVEBLOG_AUTO_DISCOVERY,
    SCANX_POLL_INTERVAL_SECONDS,
    ET_POLL_INTERVAL_SECONDS,
    MC_POLL_INTERVAL_SECONDS,
    MC_LIVE_POLL_INTERVAL_SECONDS,
    ARTICLE_TTL_HOURS,
    PRUNE_INTERVAL_SECONDS,
)
from scrapers import aljazeera, reuters
from scrapers.liveblog import scrape as scrape_liveblog
from scrapers.liveblog_discovery import discover as discover_liveblogs
from scrapers import scanx
from scrapers.economictimes import scrape_et
from scrapers.moneycontrol import scrape as scrape_mc, scrape_live as scrape_mc_live
from storage.db import init_db, is_new, mark_seen, prune_old_articles
from alerts.notifier import notify_new_article, notify_scrape_summary, notify_startup
from utils.sentiment import sentiment_worker
from dashboard.app import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

running = True

# Shared state for /api/status — updated after each cycle
last_scrape_time = None
tracked_slugs = list(TRACKED_LIVEBLOG_SLUGS)
_slugs_lock = threading.Lock()


def signal_handler(sig, frame):
    global running
    print("\n\n🛑 Shutting down gracefully...")
    running = False
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def _process_articles(articles):
    """Dedup, store, and notify for a batch of articles. Returns new count."""
    new_count = 0
    for article in articles:
        if is_new(article["url"]):
            new_count += 1
            mark_seen(article)
            notify_new_article(article, enable_desktop=ENABLE_DESKTOP_NOTIFICATIONS)
    return new_count


def scrape_cycle():
    """Run one slow scrape cycle (RSS + HTML sources + ScanX full scrape)."""
    global last_scrape_time
    all_articles = []

    try:
        all_articles.extend(aljazeera.scrape())
    except Exception as e:
        logger.error("Al Jazeera scrape failed: %s", e)

    try:
        all_articles.extend(reuters.scrape())
    except Exception as e:
        logger.error("Reuters scrape failed: %s", e)

    try:
        all_articles.extend(scanx.scrape())
    except Exception as e:
        logger.error("ScanX scrape failed: %s", e)

    new_count = _process_articles(all_articles)
    notify_scrape_summary(new_count, len(all_articles))
    last_scrape_time = datetime.now(timezone.utc)
    return new_count


def liveblog_cycle():
    """Run one fast scrape cycle (GraphQL liveblogs only)."""
    global last_scrape_time
    with _slugs_lock:
        slugs = list(tracked_slugs)

    total_new = 0
    for slug in slugs:
        try:
            articles = scrape_liveblog(slug)
            total_new += _process_articles(articles)
        except Exception as e:
            logger.error("Liveblog scrape failed [%s]: %s", slug, e)

    if total_new > 0:
        logger.info("Liveblog cycle: %d new updates across %d liveblogs", total_new, len(slugs))
    last_scrape_time = datetime.now(timezone.utc)
    return total_new


def poll_loop():
    """Slow loop: RSS + HTML every POLL_INTERVAL_SECONDS."""
    global running
    logger.info("🚀 Slow poll loop started (interval: %ds)", POLL_INTERVAL_SECONDS)
    scrape_cycle()
    while running:
        time.sleep(POLL_INTERVAL_SECONDS)
        if not running:
            break
        try:
            scrape_cycle()
        except Exception as e:
            logger.error("Slow scrape cycle error: %s", e)


def liveblog_poll_loop():
    """Fast loop: GraphQL liveblogs every LIVEBLOG_POLL_INTERVAL_SECONDS. Re-discovers every 5 min."""
    global running, tracked_slugs
    logger.info("⚡ Fast liveblog loop started (interval: %ds)", LIVEBLOG_POLL_INTERVAL_SECONDS)

    last_discovery = 0.0

    while running:
        now = time.time()
        # Re-run auto-discovery every 5 minutes
        if ENABLE_LIVEBLOG_AUTO_DISCOVERY and (now - last_discovery) > 300:
            try:
                discovered = discover_liveblogs()
                with _slugs_lock:
                    existing = set(tracked_slugs)
                    new_slugs = [s for s in discovered if s not in existing]
                    if new_slugs:
                        tracked_slugs.extend(new_slugs)
                        logger.info("Auto-discovered %d new liveblog(s): %s", len(new_slugs), new_slugs)
                last_discovery = time.time()
            except Exception as e:
                logger.error("Liveblog auto-discovery error: %s", e)

        liveblog_cycle()
        time.sleep(LIVEBLOG_POLL_INTERVAL_SECONDS)


def scanx_fast_loop():
    """Poll ScanX News Flash every SCANX_POLL_INTERVAL_SECONDS (15s)."""
    global running
    logger.info("📈 ScanX fast loop started (interval: %ds)", SCANX_POLL_INTERVAL_SECONDS)
    while running:
        try:
            articles = scanx.scrape_live()
            _process_articles(articles)
        except Exception as e:
            logger.error("ScanX fast loop error: %s", e)
        time.sleep(SCANX_POLL_INTERVAL_SECONDS)


def et_poll_loop():
    """Dedicated ET loop: polls all 25 RSS feeds every ET_POLL_INTERVAL_SECONDS (60s)."""
    global running
    logger.info("📰 ET poll loop started (interval: %ds)", ET_POLL_INTERVAL_SECONDS)
    # Run immediately on start, then on interval
    try:
        _process_articles(scrape_et())
    except Exception as e:
        logger.error("ET initial scrape error: %s", e)
    while running:
        time.sleep(ET_POLL_INTERVAL_SECONDS)
        if not running:
            break
        try:
            _process_articles(scrape_et())
        except Exception as e:
            logger.error("ET poll loop error: %s", e)


def prune_loop():
    """Periodically delete articles older than ARTICLE_TTL_HOURS."""
    global running
    logger.info("🗑️  Prune loop started (TTL: %dh, interval: %ds)", ARTICLE_TTL_HOURS, PRUNE_INTERVAL_SECONDS)
    # First prune on startup so the DB is clean immediately
    prune_old_articles(ARTICLE_TTL_HOURS)
    while running:
        time.sleep(PRUNE_INTERVAL_SECONDS)
        if not running:
            break
        prune_old_articles(ARTICLE_TTL_HOURS)


def mc_live_poll_loop():
    """Fast MC loop: polls the live market blog every MC_LIVE_POLL_INTERVAL_SECONDS (30s)."""
    global running
    logger.info("📊 MC live poll loop started (interval: %ds)", MC_LIVE_POLL_INTERVAL_SECONDS)
    try:
        _process_articles(scrape_mc_live())
    except Exception as e:
        logger.error("MC live initial scrape error: %s", e)
    while running:
        time.sleep(MC_LIVE_POLL_INTERVAL_SECONDS)
        if not running:
            break
        try:
            _process_articles(scrape_mc_live())
        except Exception as e:
            logger.error("MC live poll loop error: %s", e)


def mc_poll_loop():
    """Dedicated MC loop: polls all RSS feeds every MC_POLL_INTERVAL_SECONDS (60s)."""
    global running
    logger.info("💹 MC poll loop started (interval: %ds)", MC_POLL_INTERVAL_SECONDS)
    try:
        _process_articles(scrape_mc())
    except Exception as e:
        logger.error("MC initial scrape error: %s", e)
    while running:
        time.sleep(MC_POLL_INTERVAL_SECONDS)
        if not running:
            break
        try:
            _process_articles(scrape_mc())
        except Exception as e:
            logger.error("MC poll loop error: %s", e)


def main():
    """Main entry point."""
    notify_startup()
    init_db()
    logger.info("📦 Database ready")

    # Slow loop thread
    slow_thread = threading.Thread(target=poll_loop, daemon=True)
    slow_thread.start()
    logger.info("🔄 Slow scraper thread started")

    # Fast liveblog loop thread
    fast_thread = threading.Thread(target=liveblog_poll_loop, daemon=True)
    fast_thread.start()
    logger.info("⚡ Fast liveblog thread started")

    # ScanX fast poll thread
    scanx_thread = threading.Thread(target=scanx_fast_loop, daemon=True)
    scanx_thread.start()
    logger.info("📈 ScanX fast thread started")

    # Economic Times dedicated poll thread
    et_thread = threading.Thread(target=et_poll_loop, daemon=True)
    et_thread.start()
    logger.info("📰 ET poll thread started")

    # MoneyControl dedicated poll thread
    mc_thread = threading.Thread(target=mc_poll_loop, daemon=True)
    mc_thread.start()
    logger.info("💹 MC poll thread started")

    # MoneyControl live blog fast poll thread
    mc_live_thread = threading.Thread(target=mc_live_poll_loop, daemon=True)
    mc_live_thread.start()
    logger.info("📊 MC live poll thread started")

    # Article TTL prune thread (deletes articles older than ARTICLE_TTL_HOURS)
    prune_thread = threading.Thread(target=prune_loop, daemon=True)
    prune_thread.start()
    logger.info("🗑️  Prune thread started (TTL=%dh)", ARTICLE_TTL_HOURS)

    # Sentiment analysis worker thread (analyzes non-ScanX articles in batches)
    sentiment_thread = threading.Thread(
        target=sentiment_worker, kwargs={"interval": 60}, daemon=True
    )
    sentiment_thread.start()
    logger.info("🧠 Sentiment worker thread started")

    logger.info("🌐 Dashboard starting at http://localhost:%d", DASHBOARD_PORT)
    print(f"\n   🌐 Open http://localhost:{DASHBOARD_PORT} in your browser\n")

    app.run(
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
