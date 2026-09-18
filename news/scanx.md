ScanX.trade is an Angular SSR (Server-Side Rendered) application powered by Dhan's news backend. There is no public REST API — the news data is delivered in the HTML page source as Angular Transfer State (a large inline <script> tag containing JSON). The strategy is to fetch the page HTML, parse the transfer state JSON, and extract the articles. This gives you the same fresh data the browser sees, without needing a headless browser.
The URLs that contain news:
PageURLWhat's insideLatest (all categories)https://scanx.trade/stock-market-newsLatest, Stocks, Corporate Actions, Markets, Earnings, Orders&Deals, IPO, Global newsStockshttps://scanx.trade/stock-market-news/stocksStocks-specific newsCorporate Actionshttps://scanx.trade/stock-market-news/corporate-actionsCorporate ActionsEarningshttps://scanx.trade/stock-market-news/earningsEarningsOrders & Dealshttps://scanx.trade/stock-market-news/orders-dealsOrders & DealsMarketshttps://scanx.trade/stock-market-news/marketsMarket newsGlobalhttps://scanx.trade/stock-market-news/globalGlobal/international newsIPOhttps://scanx.trade/stock-market-news/ipoIPO newsNews Flash (LIVE FEED)https://scanx.trade/stock-market-news/news-feedsThe fastest live feed — new items every 1-2 minutesOne public API endpoint (GET, no auth needed):

https://news-live.dhan.co/news/articlenavbarlist — returns list of all categories/tabs with metadata
Article URL pattern: https://scanx.trade/stock-market-news/{article_slug}
Image URL pattern: https://news-images.dhan.co/{imageurl_field}


DATA STRUCTURE (Article Object Fields)
Each article in the transfer state has these fields:
python{
  "id": 34586306,                          # unique article ID
  "articletitle": "TCS Opens AI Center...", # title (or "title" in news-feeds)
  "summary": "Full summary text...",        # body/summary text
  "pubdate": "2026-03-09T07:18:34.472Z",   # ISO 8601 publish date (or "publish_date" as ms timestamp in news-feeds)
  "category": "stocks",                    # category
  "subcategory": "normal_news",            # sub-category
  "slug": "tcs-opens-new-gemini...",       # URL slug (or "article_slug" in news-feeds)
  "isin": "INE467B01029",                  # stock ISIN
  "sm_symbol": "TCS",                      # stock symbol
  "display_symbol": "Tata Consultancy Services",
  "imageurl": "tcs-opens-new-gemini.jpg",  # image filename (prefix with news-images.dhan.co/)
  "readtime": "1 min",
  "news_object": {                         # only in news-feeds tab
    "title": "TCS Opens AI Center...",
    "text": "Full text...",
    "overall_sentiment": "positive"        # positive/negative/neutral
  }
}

TASK 1 — Create scrapers/scanx.py
Create a new file scrapers/scanx.py with a scraper that:

Fetches the HTML of the following pages using requests.get() with a proper User-Agent header (same one used in aljazeera.py). Add "Referer": "https://scanx.trade/" to headers.
Parses the Angular Transfer State from the page HTML. The transfer state is in a <script> tag (no src attribute) that contains a large JSON object. Extract it like this:

python   from bs4 import BeautifulSoup
   import json, re
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

Find the correct key in the transfer state that contains "news-live.dhan.co/news/articlenavbardetails" or "news-live.dhan.co/v3/news/getLiveNews" in its "u" field. Example:

python   def _find_news_key(state: dict, url_fragment: str) -> dict | None:
       for key, val in state.items():
           if isinstance(val, dict) and val.get("u", "").endswith(url_fragment):
               return val.get("b", {})
       return None

The News Flash page (/stock-market-news/news-feeds) contains the v3/news/getLiveNews key. Parse its structure:

python   data = news_body["data"]["latest_news"]
   for item in data:
       title = item["news_object"]["title"]
       content = item["news_object"]["text"]
       sentiment = item["news_object"]["overall_sentiment"]
       category = item["category"]
       slug = item["article_slug"]
       published_ms = item["publish_date"]  # milliseconds timestamp
       published = datetime.utcfromtimestamp(published_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
       url = f"https://scanx.trade/stock-market-news/{slug}"
       article_id = item["article_id"]
       symbol = item.get("sm_symbol", "")

The category pages (Latest, Stocks, etc.) use articlenavbardetails. Parse their structure:

python   sections = news_body["data"]["sections_data"]
   for section in sections:
       for article in section.get("articles", []):
           title = article["articletitle"]
           content = article["summary"]
           category = article["category"]
           slug = article["slug"]
           published = article["pubdate"]  # ISO 8601 string
           url = f"https://scanx.trade/stock-market-news/{slug}"
           article_id = article["id"]
           symbol = article.get("metadata", {}).get("cm_custom_symbol", "")

Return all articles in the standard format:

python   {
       "title": title,
       "url": url,
       "source": "ScanX",
       "published": published,
       "category": f"📈 {category}",
       "content": content,
       "symbol": symbol,       # extra field for stock symbol
       "sentiment": sentiment, # only for news-feeds items
   }

The scrape() function should:

Fetch /stock-market-news/news-feeds (News Flash — fastest, scrape every 15s)
Fetch /stock-market-news (Latest — scrape every 60s)
Deduplicate by article_id (use str(article_id) as the unique key in the DB url field)
Return combined list




TASK 2 — Create scrapers/scanx_live.py (fast poll for News Flash only)
Create a dedicated fast-poll scraper just for the News Flash feed:
pythonSCANX_LIVE_URL = "https://scanx.trade/stock-market-news/news-feeds"
SCANX_POLL_INTERVAL = 15  # seconds
def scrape_live() -> list:
    """Scrape only the News Flash live feed for maximum speed."""
    # fetch, parse transfer state, find getLiveNews key, return articles

TASK 3 — Add to config.py
python# ScanX settings
SCANX_NEWS_FLASH_URL = "https://scanx.trade/stock-market-news/news-feeds"
SCANX_LATEST_URL = "https://scanx.trade/stock-market-news"
SCANX_POLL_INTERVAL_SECONDS = 15   # News Flash fast poll
SCANX_CATEGORY_URLS = [
    "https://scanx.trade/stock-market-news/stocks",
    "https://scanx.trade/stock-market-news/markets",
    "https://scanx.trade/stock-market-news/global",
    "https://scanx.trade/stock-market-news/corporate-actions",
    "https://scanx.trade/stock-market-news/earnings",
    "https://scanx.trade/stock-market-news/orders-deals",
    "https://scanx.trade/stock-market-news/ipo",
]

TASK 4 — Upgrade storage/db.py
Add symbol and sentiment columns to the articles table:
sqlALTER TABLE articles ADD COLUMN symbol TEXT DEFAULT '';
ALTER TABLE articles ADD COLUMN sentiment TEXT DEFAULT '';
Handle OperationalError if column already exists. Update mark_seen() to save these new fields. Add:
pythondef get_recent_scanx(n=100) -> list:
    """Get latest ScanX articles ordered by scraped_at."""
    ...WHERE source = 'ScanX'...

TASK 5 — Upgrade main.py
Add a third thread — the ScanX fast poll loop:
pythondef scanx_fast_loop():
    """Poll ScanX News Flash every 15 seconds."""
    global running
    logger.info("📈 ScanX fast loop started")
    while running:
        try:
            articles = scanx.scrape_live()
            for article in articles:
                if is_new(article["url"]):
                    mark_seen(article)
                    notify_new_article(article, enable_desktop=ENABLE_DESKTOP_NOTIFICATIONS)
        except Exception as e:
            logger.error("ScanX fast loop error: %s", e)
        time.sleep(SCANX_POLL_INTERVAL_SECONDS)
Also add ScanX to the existing slow poll loop (scrape_cycle()).
TASK 6 — Upgrade dashboard/app.py
Add:
python@app.route("/api/news/scanx")
def api_scanx():
    articles = get_recent_scanx(100)
    return jsonify({"articles": articles, "total": len(articles)})
Update /api/news/grouped to include scanx:
python@app.route("/api/news/grouped")
def api_news_grouped():
    return jsonify({
        "aljazeera": get_recent_by_source("Al Jazeera", 50),
        "reuters": get_recent_by_source("Reuters", 50),
        "scanx": get_recent_scanx(50),
        "total": get_article_count(),
    })

TASK 7 — Upgrade the Dashboard (index.html)
Add a third column for ScanX:

Column header: "📈 ScanX — Indian Markets" with orange/green accent
Auto-refresh the ScanX column every 10 seconds (separate timer, since it updates fastest)
Show symbol badge (e.g. TCS, WIPRO) on each card
Show sentiment indicator: green dot = positive, red = negative, grey = neutral
Show subcategory tag (e.g. "Corporate Governance", "Orders & Deals")
Change the grid to 1fr 1fr 1fr on desktop


TASK 8 — Update requirements.txt
Add lxml>=5.0.0 (already in previous plan) — required for the BeautifulSoup lxml parser used to extract the Angular transfer state.
MOST IMPORTANT IMPLEMENTATION NOTE
The key technique is this Python snippet to extract data from a ScanX page:
pythonimport requests, json, re
from bs4 import BeautifulSoup
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://scanx.trade/",
}
def fetch_scanx_page(url: str) -> list:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    # Find the Angular transfer state script (largest inline script with JSON)
    for script in soup.find_all("script", src=False):
        text = script.string or ""
        if len(text) > 5000 and '"status":200' in text:
            try:
                state = json.loads(text)
                # Find the news data key
                for key, val in state.items():
                    if isinstance(val, dict) and "news-live.dhan.co" in val.get("u", ""):
                        return val.get("b", {})
            except json.JSONDecodeError:
                continue
    return {}
This approach works because ScanX's Angular SSR pre-embeds all API responses in the HTML, so a simple requests.get() gives you full data — no Selenium, no Playwright, no headless browser needed.