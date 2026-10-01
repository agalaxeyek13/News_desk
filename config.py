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

# FDE Briefing — US-Iran daily digest
FDE_TEAM_NAME = "FDE"

# Local LLM (llama-cpp-python, GPU-offloaded) — used for entity extraction
# and synthesis instead of a cloud API.
FDE_LOCAL_MODEL_PATH = os.getenv(
    "FDE_LOCAL_MODEL_PATH",
    r"C:\Users\Galaxeye\Documents\GitHub\isrgpt-lite\models\llms\google_gemma-4-26B-A4B-it-Q4_K_M.gguf",
)
FDE_LOCAL_MODEL_CTX = int(os.getenv("FDE_LOCAL_MODEL_CTX", 4096))
FDE_LOCAL_MODEL_GPU_LAYERS = int(os.getenv("FDE_LOCAL_MODEL_GPU_LAYERS", -1))  # -1 = all layers on GPU

# One RSS feed per source. Category is used only for display grouping.
FDE_RSS_FEEDS = [
    {"source": "DoD",              "category": "Official",   "url": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=20"},
    {"source": "Defense News",     "category": "Trade Press", "url": "https://www.defensenews.com/arc/outboundfeeds/rss/category/pentagon/?outputType=xml"},
    {"source": "Breaking Defense", "category": "Trade Press", "url": "https://breakingdefense.com/feed/"},
    {"source": "The War Zone",     "category": "Trade Press", "url": "https://www.twz.com/feed"},
    {"source": "Long War Journal", "category": "Analysis",   "url": "https://www.longwarjournal.org/feed"},
    {"source": "Atlantic Council", "category": "Analysis",   "url": "https://www.atlanticcouncil.org/feed/"},
    {"source": "RAND",             "category": "Analysis",   "url": "https://www.rand.org/content/rand/pubs.xml"},
    {"source": "Al-Monitor",       "category": "Regional",   "url": "https://www.al-monitor.com/rss.xml"},
    {"source": "Times of Israel",  "category": "Regional",   "url": "https://www.timesofisrael.com/feed/"},
    {"source": "Middle East Eye",  "category": "Regional",   "url": "https://www.middleeasteye.net/rss"},
    {"source": "Naval News",       "category": "Trade Press", "url": "https://www.navalnews.com/feed/"},
    {"source": "The Aviationist",  "category": "Trade Press", "url": "https://theaviationist.com/feed/"},
]

# How far back an article can be published and still count as "today's" news
FDE_RECENCY_HOURS = int(os.getenv("FDE_RECENCY_HOURS", 24))

# Opinion / commentary is never written up as a briefing section — it's
# listed under "Opinion & Commentary" instead. Matched against the URL.
FDE_OPINION_MARKERS = [
    "/opinion", "/opinions/", "/commentary/", "/op-ed", "/oped/", "/editorial",
    "/blogs/", "/dispatches/", "/podcast",
]

# General-news sources whose full feeds cover sports, entertainment, etc.
# Only their US-Iran-relevant items are listed; every other source lists
# everything it published in the window.
FDE_GENERAL_NEWS_SOURCES = ["Al Jazeera", "Reuters"]

# Times in the email are shown in this zone (default IST, UTC+5:30).
FDE_DISPLAY_TZ_OFFSET_MINUTES = int(os.getenv("FDE_DISPLAY_TZ_OFFSET_MINUTES", 330))
FDE_DISPLAY_TZ_LABEL = os.getenv("FDE_DISPLAY_TZ_LABEL", "IST")

# ISW's Iran Update has no RSS — scraped from this listing page instead.
FDE_ISW_LISTING_URL = "https://www.understandingwar.org/backgrounder/iran-update"

# Cheap keyword gate applied before any LLM call — must match at least one.
# Covers the Iran-linked actors and theater, not just the word "Iran":
# a Houthi strike on Saudi shipping or an IRGC-backed militia attack in
# Iraq is part of this conflict and was being dropped without these.
FDE_KEYWORDS = [
    # Iran proper
    "iran", "iranian", "tehran", "irgc", "khamenei", "pezeshkian",
    "quds force", "revolutionary guard", "bandar abbas", "natanz", "fordow",
    "mahan air", "artesh", "basij",
    # Waterways / theater
    "hormuz", "persian gulf", "gulf of oman", "red sea", "bab al-mandeb",
    "bab el-mandeb", "strait of tiran",
    # US military presence
    "centcom", "central command", "fifth fleet", "al udeid",
    # Iran-aligned actors
    "houthi", "hezbollah", "kataib", "popular mobilization",
    "islamic resistance in iraq", "ansar allah",
    # Regional states central to this conflict.
    # Deliberately NOT "israel"/"israeli": Israel-Iran stories already match
    # on "iran", while those words on their own pull in the whole
    # Gaza/West Bank domestic news cycle, which is not this briefing.
    "yemen", "saudi arabia", "saudi", "iraq", "iraqi",
]

# Comma-separated internal recipient list, e.g. "a@company.com,b@company.com"
FDE_RECIPIENTS = [e.strip() for e in os.getenv("FDE_RECIPIENTS", "").split(",") if e.strip()]
FDE_SENDER = os.getenv("FDE_SENDER", "")

# Outlook / Microsoft 365 SMTP
FDE_SMTP_HOST = os.getenv("FDE_SMTP_HOST", "smtp.office365.com")
FDE_SMTP_PORT = int(os.getenv("FDE_SMTP_PORT", 587))
FDE_SMTP_USER = os.getenv("FDE_SMTP_USER", "")
FDE_SMTP_PASSWORD = os.getenv("FDE_SMTP_PASSWORD", "")

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
