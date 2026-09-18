"""
Notification system — desktop alerts & coloured console output.
"""

import logging
import sys

logger = logging.getLogger(__name__)

# ANSI colour codes
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _try_desktop_notification(title, message, timeout=10):
    """Attempt to send a desktop notification via plyer."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="News Alert",
            timeout=timeout,
        )
    except Exception as e:
        # Desktop notifications may not work in all environments
        logger.debug("Desktop notification failed (non-critical): %s", e)


def notify_new_article(article, enable_desktop=True):
    """
    Alert the user about a new article.
    - Prints a coloured console message
    - Sends a desktop notification if enabled
    """
    source = article.get("source", "Unknown")
    title = article.get("title", "No title")
    url = article.get("url", "")
    published = article.get("published", "")

    # Colour-coded console output
    if source == "Al Jazeera":
        source_colour = YELLOW
    elif source == "Reuters":
        source_colour = CYAN
    else:
        source_colour = GREEN

    print(
        f"\n{GREEN}🔔 NEW{RESET} "
        f"{source_colour}{BOLD}[{source}]{RESET} "
        f"{BOLD}{title}{RESET}"
    )
    if published:
        print(f"   📅 {published}")
    print(f"   🔗 {url}")

    # Desktop notification
    if enable_desktop:
        _try_desktop_notification(
            title=f"🔔 {source}",
            message=title[:200],
        )


def notify_scrape_summary(new_count, total_scraped, source_name="All"):
    """Print a summary of the scrape cycle."""
    if new_count > 0:
        print(
            f"\n{GREEN}✅ {new_count} new article(s){RESET} "
            f"from {BOLD}{source_name}{RESET} "
            f"(checked {total_scraped} total)"
        )
    else:
        print(
            f"\n{CYAN}ℹ️  No new articles{RESET} "
            f"from {BOLD}{source_name}{RESET} "
            f"(checked {total_scraped} total)"
        )


def notify_startup():
    """Print startup banner."""
    banner = f"""
{GREEN}{BOLD}╔══════════════════════════════════════════════╗
║        📰  NEWS ALERT SYSTEM  📰            ║
║   Al Jazeera  •  Reuters  •  Live Updates    ║
╚══════════════════════════════════════════════╝{RESET}
"""
    print(banner)
