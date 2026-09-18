"""
ScanX fast-poll scraper — News Flash feed only.
Imports the core logic from scanx.py and exposes scrape_live()
as a standalone module for use in dedicated fast-poll loops.
"""

from scrapers.scanx import scrape_live, SCANX_NEWS_FLASH_URL  # noqa: F401

SCANX_POLL_INTERVAL = 15  # seconds
