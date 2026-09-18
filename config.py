"""
Configuration for the News Alert System.
Loads overrides from .env if present.
"""
from dotenv import load_dotenv
import os

load_dotenv()

# Poll intervals
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", 120))
LIVEBLOG_POLL_INTERVAL_SECONDS = int(os.getenv("LIVEBLOG_POLL_INTERVAL_SECONDS", 15))

# Desktop notification settings
ENABLE_DESKTOP_NOTIFICATIONS = os.getenv("ENABLE_DESKTOP_NOTIFICATIONS", "true").lower() == "true"
NOTIFICATION_TIMEOUT = 10  # seconds

# Dashboard settings
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 5050))

# Data sources
ALJAZEERA_RSS_URL = "https://www.aljazeera.com/xml/rss/all.xml"
REUTERS_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"
ALJAZEERA_GRAPHQL_URL = "https://www.aljazeera.com/graphql"

# Liveblog settings
TRACKED_LIVEBLOG_SLUGS = []           # Manually tracked slugs (auto-discovery adds to these)
ENABLE_LIVEBLOG_AUTO_DISCOVERY = True # Auto-find active liveblogs from homepage

# Database
DB_PATH = "news.db"
ARTICLE_TTL_HOURS = int(os.getenv("ARTICLE_TTL_HOURS", 6))   # articles older than this are deleted
PRUNE_INTERVAL_SECONDS = int(os.getenv("PRUNE_INTERVAL_SECONDS", 1800))  # prune every 30 min

# Max articles to show on dashboard
MAX_DASHBOARD_ARTICLES = 100

# Retry / resilience settings
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 20

# Notification settings
ENABLE_SOUND_ALERT = False
MIN_NOTIFICATION_INTERVAL_SECONDS = 2

# MoneyControl
MC_POLL_INTERVAL_SECONDS = int(os.getenv("MC_POLL_INTERVAL_SECONDS", 60))
MC_LIVE_POLL_INTERVAL_SECONDS = int(os.getenv("MC_LIVE_POLL_INTERVAL_SECONDS", 30))
MC_RSS_FEEDS = [
    {"url": "https://www.moneycontrol.com/rss/latestnews.xml",    "category": "Latest News"},
    {"url": "https://www.moneycontrol.com/rss/MCtopnews.xml",     "category": "Top News"},
    {"url": "https://www.moneycontrol.com/rss/buzzingstocks.xml", "category": "Buzzing Stocks"},
    {"url": "https://www.moneycontrol.com/rss/economy.xml",       "category": "Economy"},
    {"url": "https://www.moneycontrol.com/rss/business.xml",      "category": "Business"},
    {"url": "https://www.moneycontrol.com/rss/commodities.xml",   "category": "Commodities"},
]

# Economic Times
ET_POLL_INTERVAL_SECONDS = int(os.getenv("ET_POLL_INTERVAL_SECONDS", 60))
ET_FEEDS = {
    "top_stories":         "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "latest_news":         "https://economictimes.indiatimes.com/rssfeedslatest.cms",
    "most_read":           "https://economictimes.indiatimes.com/rssfeedsmostread.cms",
    "markets":             "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "stocks":              "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "ipos":                "https://economictimes.indiatimes.com/markets/ipos/fpos/rssfeeds/2146842.cms",
    "commodities":         "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808152989.cms",
    "forex":               "https://economictimes.indiatimes.com/markets/forex/rssfeeds/1808152992.cms",
    "bonds":               "https://economictimes.indiatimes.com/markets/bonds/rssfeeds/1808152993.cms",
    "mutual_funds":        "https://economictimes.indiatimes.com/mf/rssfeeds/1977021501.cms",
    "news_india":          "https://economictimes.indiatimes.com/news/india/rssfeeds/1052732854.cms",
    "news_politics":       "https://economictimes.indiatimes.com/news/politics-and-nation/rssfeeds/1052732854.cms",
    "news_defence":        "https://economictimes.indiatimes.com/news/defence/rssfeeds/76245804.cms",
    "news_international":  "https://economictimes.indiatimes.com/news/international/rssfeeds/1580288.cms",
    "news_economy":        "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "news_eco_policy":     "https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1373380681.cms",
    "news_eco_finance":    "https://economictimes.indiatimes.com/news/economy/finance/rssfeeds/1373380682.cms",
    "news_eco_indicators": "https://economictimes.indiatimes.com/news/economy/indicators/rssfeeds/1373380683.cms",
    "industry":            "https://economictimes.indiatimes.com/industry/rssfeeds/1977021501.cms",
    "tech":                "https://economictimes.indiatimes.com/tech/rssfeeds/1977021501.cms",
    "startups":            "https://economictimes.indiatimes.com/startups/rssfeeds/1977021501.cms",
    "wealth":              "https://economictimes.indiatimes.com/wealth/rssfeeds/1977021501.cms",
    "small_biz":           "https://economictimes.indiatimes.com/small-biz/rssfeeds/1977021501.cms",
    "et_now":              "https://economictimes.indiatimes.com/et-now/rssfeeds/1977021501.cms",
    "sports":              "https://economictimes.indiatimes.com/sports/rssfeeds/1977021501.cms",
}

# ScanX settings
SCANX_NEWS_FLASH_URL = "https://scanx.trade/stock-market-news/news-feeds"
SCANX_LATEST_URL = "https://scanx.trade/stock-market-news"
SCANX_POLL_INTERVAL_SECONDS = int(os.getenv("SCANX_POLL_INTERVAL_SECONDS", 15))
SCANX_CATEGORY_URLS = [
    "https://scanx.trade/stock-market-news/stocks",
    "https://scanx.trade/stock-market-news/markets",
    "https://scanx.trade/stock-market-news/global",
    "https://scanx.trade/stock-market-news/corporate-actions",
    "https://scanx.trade/stock-market-news/earnings",
    "https://scanx.trade/stock-market-news/orders-deals",
    "https://scanx.trade/stock-market-news/ipo",
]
