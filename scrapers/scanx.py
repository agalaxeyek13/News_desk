"""
ScanX (scanx.trade) news scraper — extracts articles from Angular SSR Transfer State.
ScanX is powered by Dhan's news backend. Data is embedded in the HTML as a large
inline <script> tag (Angular Transfer State), so no headless browser is needed.

Scrapes:
  - /stock-market-news/news-feeds  → News Flash live feed   (fast, every 15s)
  - /stock-market-news             → Latest across all tabs  (slow, every 60s)
"""

import requests
import json
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SCANX_NEWS_FLASH_URL = "https://scanx.trade/stock-market-news/news-feeds"
SCANX_LATEST_URL = "https://scanx.trade/stock-market-news"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://scanx.trade/",
}


def _extract_transfer_state(html: str) -> dict:
    """Extract Angular SSR transfer state from page HTML."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", src=False):
        text = script.string or ""
        if len(text) > 5000 and '"status":200' in text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
    return {}


def _find_news_key(state: dict, url_fragment: str) -> dict | None:
    """Find the transfer state key whose 'u' field ends with url_fragment."""
    for key, val in state.items():
        if isinstance(val, dict) and val.get("u", "").endswith(url_fragment):
            return val.get("b", {})
    return None


def _parse_news_flash(news_body: dict) -> list:
    """Parse articles from the News Flash (/news-feeds) getLiveNews structure."""
    articles = []
    try:
        items = news_body.get("data", {}).get("latest_news", [])
        for item in items:
            try:
                news_obj = item.get("news_object", {})
                title = news_obj.get("title", "").strip()
                content = news_obj.get("text", "").strip()
                sentiment = news_obj.get("overall_sentiment", "neutral")
                category = item.get("category", "")
                slug = item.get("article_slug", "")
                article_id = str(item.get("article_id", ""))
                symbol = item.get("sm_symbol", "")

                published_ms = item.get("publish_date")
                if published_ms:
                    published = datetime.utcfromtimestamp(published_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                if not title or not article_id:
                    continue

                url = f"https://scanx.trade/stock-market-news/{slug}" if slug else f"scanx:{article_id}"

                articles.append({
                    "title": title,
                    "url": url,
                    "source": "ScanX",
                    "published": published,
                    "category": f"📈 {category}" if category else "📈 News Flash",
                    "content": content,
                    "symbol": symbol,
                    "sentiment": sentiment,
                })
            except Exception as e:
                logger.debug("Skipping news flash item: %s", e)
    except Exception as e:
        logger.error("Error parsing news flash data: %s", e)
    return articles


def _parse_category_page(news_body: dict) -> list:
    """Parse articles from a category page (articlenavbardetails structure)."""
    articles = []
    try:
        sections = news_body.get("data", {}).get("sections_data", [])
        for section in sections:
            for article in section.get("articles", []):
                try:
                    title = article.get("articletitle", "").strip()
                    content = article.get("summary", "").strip()
                    category = article.get("category", "")
                    slug = article.get("slug", "")
                    article_id = str(article.get("id", ""))
                    published = article.get("pubdate", "")
                    symbol = article.get("metadata", {}).get("cm_custom_symbol", "") or article.get("sm_symbol", "")

                    if not title or not article_id:
                        continue

                    url = f"https://scanx.trade/stock-market-news/{slug}" if slug else f"scanx:{article_id}"

                    articles.append({
                        "title": title,
                        "url": url,
                        "source": "ScanX",
                        "published": published,
                        "category": f"📈 {category}" if category else "📈 Market",
                        "content": content,
                        "symbol": symbol,
                        "sentiment": "",
                    })
                except Exception as e:
                    logger.debug("Skipping category article: %s", e)
    except Exception as e:
        logger.error("Error parsing category page data: %s", e)
    return articles


def _fetch_page(url: str) -> list:
    """Fetch a ScanX page and return parsed articles."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        logger.error("ScanX fetch error [%s]: %s", url, e)
        return []

    state = _extract_transfer_state(resp.text)
    if not state:
        logger.warning("No transfer state found at %s", url)
        return []

    # News Flash uses getLiveNews key
    if "news-feeds" in url:
        news_body = _find_news_key(state, "getLiveNews")
        if news_body is None:
            # Fallback: try any key with getLiveNews anywhere in the URL
            for key, val in state.items():
                if isinstance(val, dict) and "getLiveNews" in val.get("u", ""):
                    news_body = val.get("b", {})
                    break
        if news_body:
            return _parse_news_flash(news_body)
    else:
        # Category/latest pages use articlenavbardetails
        news_body = _find_news_key(state, "articlenavbardetails")
        if news_body is None:
            for key, val in state.items():
                if isinstance(val, dict) and "articlenavbardetails" in val.get("u", ""):
                    news_body = val.get("b", {})
                    break
        if news_body:
            return _parse_category_page(news_body)

    logger.warning("Could not find news data key at %s", url)
    return []


def scrape_live() -> list:
    """Scrape only the News Flash live feed (fast poll — call every 15s)."""
    articles = _fetch_page(SCANX_NEWS_FLASH_URL)
    logger.info("ScanX News Flash: %d articles", len(articles))
    return articles


def scrape() -> list:
    """
    Full scrape: News Flash + Latest page.
    Deduplicates by article URL. Call this in the slow poll loop (every 60s).
    """
    seen_urls = set()
    all_articles = []

    # News Flash (live feed)
    for article in _fetch_page(SCANX_NEWS_FLASH_URL):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    # Latest page (category overview)
    for article in _fetch_page(SCANX_LATEST_URL):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    logger.info("ScanX total: %d unique articles", len(all_articles))
    return all_articles
