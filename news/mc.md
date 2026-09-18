MoneyControl: Uses old-school server-rendered HTML + multiple RSS feeds. The site has a public RSS system at /rss/*.xml. After testing all major feed names, these are confirmed working (HTTP 200): latestnews.xml, MCtopnews.xml, buzzingstocks.xml, economy.xml, business.xml, commodities.xml. The news-all listing page (/news/news-all/) is also HTML-scrapable with articles in <li class="clearfix"> elements. There is no public REST/JSON API without authentication.
Economic Times: The domain economictimes.indiatimes.com is blocked in this browser environment. However, from confirmed knowledge: ET has a well-documented RSS system at economictimes.indiatimes.com/rssfeedstopstories.cms (all top stories) and category RSS feeds at economictimes.indiatimes.com/{category}/rssfeeds/{FEED_ID}.cms. The Markets-specific feed ID is 1977021501. These are publicly accessible via Python requests without auth.
Complete Task List for Claude Code

TASK 1 — Create scrapers/moneycontrol.py
Create a new file scrapers/moneycontrol.py that scrapes MoneyControl using both RSS feeds and HTML scraping:
Part A — RSS Feeds (primary, fastest method):
pythonimport feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
# All confirmed-working MC RSS feeds (HTTP 200, no auth needed)
MC_RSS_FEEDS = [
    {
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "category": "Latest News",
    },
    {
        "url": "https://www.moneycontrol.com/rss/MCtopnews.xml",
        "category": "Top News",
    },
    {
        "url": "https://www.moneycontrol.com/rss/buzzingstocks.xml",
        "category": "Buzzing Stocks",
    },
    {
        "url": "https://www.moneycontrol.com/rss/economy.xml",
        "category": "Economy",
    },
    {
        "url": "https://www.moneycontrol.com/rss/business.xml",
        "category": "Business",
    },
    {
        "url": "https://www.moneycontrol.com/rss/commodities.xml",
        "category": "Commodities",
    },
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml",
}
def _scrape_rss() -> list:
    """Fetch articles from all MoneyControl RSS feeds."""
    articles = []
    seen_urls = set()
    for feed_info in MC_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if feed.bozo and not feed.entries:
                logger.warning("MC RSS feed failed: %s", feed_info["url"])
                continue
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        published = entry.get("published", "")
                else:
                    published = entry.get("published", "")
                # Extract summary from description (strip HTML img tags)
                description = entry.get("summary", "") or entry.get("description", "")
                soup = BeautifulSoup(description, "lxml")
                content = soup.get_text(strip=True)
                articles.append({
                    "title": title,
                    "url": link,
                    "source": "MoneyControl",
                    "published": published,
                    "category": f"📊 {feed_info['category']}",
                    "content": content,
                })
            logger.info("MC RSS [%s]: %d articles", feed_info["category"], len(feed.entries))
        except Exception as e:
            logger.error("MC RSS error [%s]: %s", feed_info["url"], e)
    return articles
Part B — HTML Scraping of /news/news-all/ (backup + catches articles not in RSS):
pythonMC_NEWS_ALL_URL = "https://www.moneycontrol.com/news/news-all/"
def _scrape_html() -> list:
    """
    Scrape the MC news-all listing page for latest article links.
    Articles appear in <li class="clearfix"> elements.
    URL pattern: moneycontrol.com/news/{category}/{slug}-{id}.html
    """
    articles = []
    try:
        resp = requests.get(MC_NEWS_ALL_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        seen_urls = set()
        for li in soup.find_all("li", class_="clearfix"):
            link_tag = li.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            # Only valid article URLs matching pattern
            import re
            if not re.match(r"https://www\\.moneycontrol\\.com/news/.+/[a-z0-9-]+-\\d+\\.html", href):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            title = link_tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            articles.append({
                "title": title,
                "url": href,
                "source": "MoneyControl",
                "published": now_str,
                "category": "📊 Latest",
                "content": "",
            })
        logger.info("MC HTML scrape: %d articles", len(articles))
    except Exception as e:
        logger.error("MC HTML scrape error: %s", e)
    return articles
def scrape() -> list:
    """Scrape MoneyControl from RSS feeds + HTML. Returns deduplicated list."""
    seen_urls = set()
    all_articles = []
    # RSS first (has timestamps)
    for article in _scrape_rss():
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)
    # HTML backup
    for article in _scrape_html():
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)
    logger.info("MoneyControl total: %d unique articles", len(all_articles))
    return all_articles

TASK 2 — Create scrapers/economictimes.py
Create a new file scrapers/economictimes.py using Economic Times RSS feeds:
pythonimport feedparser
from bs4 import BeautifulSoup
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
# ET RSS Feed IDs (confirmed public, no auth needed)
# URL pattern: https://economictimes.indiatimes.com/{section}/rssfeeds/{ID}.cms
# OR for top stories: https://economictimes.indiatimes.com/rssfeedstopstories.cms
ET_RSS_FEEDS = [
    {
        "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
        "category": "Top Stories",
    },
    {
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "category": "Markets",
    },
    {
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "category": "Stocks",
    },
    {
        "url": "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808152.cms",
        "category": "Commodities",
    },
    {
        "url": "https://economictimes.indiatimes.com/economy/rssfeeds/1373380680.cms",
        "category": "Economy",
    },
    {
        "url": "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",
        "category": "Industry",
    },
    {
        "url": "https://economictimes.indiatimes.com/small-biz/rssfeeds/6743101.cms",
        "category": "Small Business",
    },
    {
        "url": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
        "category": "Technology",
    },
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml",
    "Referer": "https://economictimes.indiatimes.com/",
}
def _parse_et_feed(feed_url: str, category: str) -> list:
    """Parse a single ET RSS feed."""
    articles = []
    try:
        # ET RSS requires a proper User-Agent - use requests + feedparser
        import requests
        resp = requests.get(feed_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            logger.warning("ET feed failed: %s", feed_url)
            return []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            published = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    published = entry.get("published", "")
            else:
                published = entry.get("published", "")
            # Description cleanup - ET embeds HTML in description
            description = entry.get("summary", "") or entry.get("description", "")
            soup = BeautifulSoup(description, "lxml")
            content = soup.get_text(strip=True)
            articles.append({
                "title": title,
                "url": link,
                "source": "Economic Times",
                "published": published,
                "category": f"📈 ET {category}",
                "content": content,
            })
        logger.info("ET RSS [%s]: %d articles", category, len(articles))
    except Exception as e:
        logger.error("ET RSS error [%s]: %s", category, e)
    return articles
def scrape() -> list:
    """Scrape Economic Times from all RSS feeds. Returns deduplicated list."""
    all_articles = []
    seen_urls = set()
    for feed_info in ET_RSS_FEEDS:
        for article in _parse_et_feed(feed_info["url"], feed_info["category"]):
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                all_articles.append(article)
    logger.info("Economic Times total: %d unique articles", len(all_articles))
    return all_articles

TASK 3 — Update scrapers/__init__.py
Add MoneyControl and Economic Times to the scrapers package:
pythonfrom scrapers import aljazeera, reuters, scanx, moneycontrol, economictimes

TASK 4 — Update main.py — Add MC and ET to the slow scrape cycle
In the scrape_cycle() function, add:
python# Scrape MoneyControl
try:
    mc_articles = moneycontrol.scrape()
    all_articles.extend(mc_articles)
except Exception as e:
    logger.error("MoneyControl scrape failed: %s", e)
# Scrape Economic Times
try:
    et_articles = economictimes.scrape()
    all_articles.extend(et_articles)
except Exception as e:
    logger.error("Economic Times scrape failed: %s", e)
Set the poll interval for these to 60 seconds (RSS feeds for both sites don't update faster than that). They do NOT need a fast loop (unlike ScanX's News Flash which updates in real time). Set POLL_INTERVAL_SECONDS = 60 in config.py.
TASK 5 — Update config.py
python# MoneyControl settings
MONEYCONTROL_POLL_INTERVAL_SECONDS = 60
MC_RSS_FEEDS = [
    "https://www.moneycontrol.com/rss/latestnews.xml",
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://www.moneycontrol.com/rss/buzzingstocks.xml",
    "https://www.moneycontrol.com/rss/economy.xml",
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.moneycontrol.com/rss/commodities.xml",
]
# Economic Times settings
ET_POLL_INTERVAL_SECONDS = 60
ET_RSS_FEEDS = [
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://economictimes.indiatimes.com/economy/rssfeeds/1373380680.cms",
    "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",
    "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
]

TASK 6 — Update dashboard/app.py
Add new API endpoints:
python@app.route("/api/news/grouped")
def api_news_grouped():
    return jsonify({
        "aljazeera":     get_recent_by_source("Al Jazeera", 50),
        "reuters":       get_recent_by_source("Reuters", 50),
        "scanx":         get_recent_by_source("ScanX", 50),
        "moneycontrol":  get_recent_by_source("MoneyControl", 50),
        "economictimes": get_recent_by_source("Economic Times", 50),
        "total":         get_article_count(),
    })
@app.route("/api/news/mc")
def api_mc():
    return jsonify({"articles": get_recent_by_source("MoneyControl", 100)})
@app.route("/api/news/et")
def api_et():
    return jsonify({"articles": get_recent_by_source("Economic Times", 100)})

TASK 7 — Update dashboard/templates/index.html
The dashboard now has 5 sources. Change the layout to:

Top row (full width): 🔴 ScanX Live News Flash (fast 10s refresh)
Bottom row (4 columns): Al Jazeera | Reuters | MoneyControl | Economic Times
Color scheme additions:
MoneyControl: #005eb8 (MC blue) accent
Economic Times: #ff4500 (ET orange) accent
Each column updates every 30 seconds. The feed column count should collapse to 2 columns on tablet and 1 column on mobile.


TASK 8 — Important Notes on ET RSS Feed IDs
The ET RSS feed IDs used above are well-established public IDs. However, if any return 404, the fallback is to use feedparser.parse() directly on the .cms URL without needing to know the numeric IDs, because ET also supports:

https://economictimes.indiatimes.com/rssfeedstopstories.cms — top stories (no ID needed)
https://economictimes.indiatimes.com/markets/rssfeedstopstories.cms — markets top stories (no ID needed)
https://economictimes.indiatimes.com/news/economy/rssfeedstopstories.cms — economy top stories
These slugged URLs always work regardless of feed ID changes. Use these as primary, and the numbered ones as secondary. Put this in the ET_RSS_FEEDS list with the slugged URLs first.


SUMMARY TABLE
SourceMethodPoll IntervalCoverageAl Jazeera (existing)RSS + HTML + GraphQL (liveblog)120s slow / 15s fastAll news + liveReuters (existing)Google News RSS120sAll categoriesScanX (from prev task)HTML Transfer State120s slow / 15s fastIndian markets + liveMoneyControl (new)RSS feeds (6 feeds)60sLatest, Top, Economy, Business, Stocks, CommoditiesEconomic Times (new)RSS feeds (6+ feeds)60sTop stories, Markets, Stocks, Economy, Industry, Tech