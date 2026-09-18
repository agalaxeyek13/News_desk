Economic Times — Full-Site Claude Code Task List
Research findings (verified live, 09 Mar 2026):
Method: RSS 2.0 feeds — direct HTTP GET from Python, no auth, no API key needed. ET blocks CORS from browsers but accepts plain requests.get() with a browser User-Agent.
RSS fields confirmed from live feeds:

item.title — article headline
item.link — canonical article URL (pattern: https://economictimes.indiatimes.com/{section}/{slug}/articleshow/{msid}.cms)
item.guid — same as link, use as dedup key
item.pubDate — RFC 2822 datetime string e.g. "Mon, 09 Mar 2026 11:33:03 +0530"
item.description — HTML snippet with thumbnail <img> + text summary
item.thumbnail (in markets feed) — http://timesofindia.indiatimes.com/photo/{msid}.cms
No author, no categories populated in any feed (empty strings/arrays)
Important: rssfeedstopstories.cms returns ~10 items with NO description/thumbnail. markets/rssfeeds/1977021501.cms returns ~10 items WITH description+thumbnail. Always use the section-specific feeds for richer content.
Article URL pattern extracted: https://economictimes.indiatimes.com/{section}/{subsection}/articleshow/{msid}.cms
The numeric msid at end is the article's unique ID — use this as the dedup key, not the full URL (which can vary in slug).


Task 1 — Create scrapers/economictimes.py
Create a new file scrapers/economictimes.py. This is a standalone multi-feed RSS scraper that polls all ET sections every 60 seconds.
FEEDS dict — map category label → RSS URL:
'top_stories'         → https://economictimes.indiatimes.com/rssfeedstopstories.cms
'latest_news'         → https://economictimes.indiatimes.com/rssfeedslatest.cms
'most_read'           → https://economictimes.indiatimes.com/rssfeedsmostread.cms
'markets'             → https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms
'stocks'              → https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms
'ipos'                → https://economictimes.indiatimes.com/markets/ipos/fpos/rssfeeds/2146842.cms
'commodities'         → https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808152989.cms
'forex'               → https://economictimes.indiatimes.com/markets/forex/rssfeeds/1808152992.cms
'bonds'               → https://economictimes.indiatimes.com/markets/bonds/rssfeeds/1808152993.cms
'mutual_funds'        → https://economictimes.indiatimes.com/mf/rssfeeds/1977021501.cms
'news_india'          → https://economictimes.indiatimes.com/news/india/rssfeeds/1052732854.cms
'news_politics'       → https://economictimes.indiatimes.com/news/politics-and-nation/rssfeeds/1052732854.cms
'news_defence'        → https://economictimes.indiatimes.com/news/defence/rssfeeds/76245804.cms
'news_international'  → https://economictimes.indiatimes.com/news/international/rssfeeds/1580288.cms
'news_economy'        → https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms
'news_eco_policy'     → https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1373380681.cms
'news_eco_finance'    → https://economictimes.indiatimes.com/news/economy/finance/rssfeeds/1373380682.cms
'news_eco_indicators' → https://economictimes.indiatimes.com/news/economy/indicators/rssfeeds/1373380683.cms
'industry'            → https://economictimes.indiatimes.com/industry/rssfeeds/1977021501.cms
'tech'                → https://economictimes.indiatimes.com/tech/rssfeeds/1977021501.cms
'startups'            → https://economictimes.indiatimes.com/startups/rssfeeds/1977021501.cms
'wealth'              → https://economictimes.indiatimes.com/wealth/rssfeeds/1977021501.cms
'small_biz'           → https://economictimes.indiatimes.com/small-biz/rssfeeds/1977021501.cms
'et_now'              → https://economictimes.indiatimes.com/et-now/rssfeeds/1977021501.cms
'sports'              → https://economictimes.indiatimes.com/sports/rssfeeds/1977021501.cms
scrape_et() function logic:

Import feedparser, re, logging, time from standard lib.
HTTP session setup — ET blocks default Python requests UA. Use feedparser with a custom agent string. Pass request_headers={'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'} to every feedparser.parse() call.
For each (category, url) in FEEDS:

Call feedparser.parse(url, request_headers={...})
If feed.status is not 200, log warning and continue
For each entry in feed.entries:

Extract msid from the URL using regex: re.search(r'/articleshow/(\\d+)\\.cms', entry.link) — group(1) is the unique article ID. Use "ET_" + msid as the article_id for dedup.
If msid not found, fall back to entry.guid as the key.
Build article dict:





       {
         'title':     entry.get('title', '').strip(),
         'url':       entry.get('link', ''),
         'source':    'Economic Times',
         'published': entry.get('published', ''),
         'category':  category,  # e.g. 'markets', 'news_politics'
         'content':   BeautifulSoup(entry.get('summary', ''), 'html.parser').get_text(strip=True),
       }
 - Content: the `description` field in ET RSS contains HTML (`<a href...><img...>text</a>`). Strip HTML with BeautifulSoup to get plain text summary. Import `from bs4 import BeautifulSoup`.
 - Thumbnail: extract the `src` attribute from the `<img>` tag inside `description` using BeautifulSoup: `soup.find('img')['src']` — store in `article['thumbnail']` (add column, see Task 2).
4. scrape_et() returns list[dict] — one dict per article. Do NOT deduplicate inside the scraper; that's handled by storage/db.py.
5. Wrap entire function body in try/except Exception as e: logging.error(f"ET scrape error: {e}") — must not raise.
get_msid(url: str) -> str | None helper:
def get_msid(url):
    m = re.search(r'/articleshow/(\\d+)\\.cms', url)
    return m.group(1) if m else None

Task 2 — Update storage/db.py
In init_db(), add two new columns to the articles table if they don't already exist:
sqlALTER TABLE articles ADD COLUMN IF NOT EXISTS thumbnail TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS msid TEXT;
Also update is_new(article_id) and mark_seen(article_id) — no change needed since they already use article_id as the dedup key. The ET scraper sets article_id = "ET_" + msid, which is globally unique and collision-safe across sources.
Task 3 — Update config.py
Add the following ET-specific configuration constants:
python# Economic Times
ET_POLL_INTERVAL = 60  # seconds — RSS feeds update every 1-5 min
ET_FEEDS = {
    'top_stories':         'https://economictimes.indiatimes.com/rssfeedstopstories.cms',
    'latest_news':         'https://economictimes.indiatimes.com/rssfeedslatest.cms',
    'most_read':           'https://economictimes.indiatimes.com/rssfeedsmostread.cms',
    'markets':             'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
    'stocks':              'https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms',
    'ipos':                'https://economictimes.indiatimes.com/markets/ipos/fpos/rssfeeds/2146842.cms',
    'commodities':         'https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808152989.cms',
    'forex':               'https://economictimes.indiatimes.com/markets/forex/rssfeeds/1808152992.cms',
    'bonds':               'https://economictimes.indiatimes.com/markets/bonds/rssfeeds/1808152993.cms',
    'mutual_funds':        'https://economictimes.indiatimes.com/mf/rssfeeds/1977021501.cms',
    'news_india':          'https://economictimes.indiatimes.com/news/india/rssfeeds/1052732854.cms',
    'news_politics':       'https://economictimes.indiatimes.com/news/politics-and-nation/rssfeeds/1052732854.cms',
    'news_defence':        'https://economictimes.indiatimes.com/news/defence/rssfeeds/76245804.cms',
    'news_international':  'https://economictimes.indiatimes.com/news/international/rssfeeds/1580288.cms',
    'news_economy':        'https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms',
    'news_eco_policy':     'https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1373380681.cms',
    'news_eco_finance':    'https://economictimes.indiatimes.com/news/economy/finance/rssfeeds/1373380682.cms',
    'news_eco_indicators': 'https://economictimes.indiatimes.com/news/economy/indicators/rssfeeds/1373380683.cms',
    'industry':            'https://economictimes.indiatimes.com/industry/rssfeeds/1977021501.cms',
    'tech':                'https://economictimes.indiatimes.com/tech/rssfeeds/1977021501.cms',
    'startups':            'https://economictimes.indiatimes.com/startups/rssfeeds/1977021501.cms',
    'wealth':              'https://economictimes.indiatimes.com/wealth/rssfeeds/1977021501.cms',
    'small_biz':           'https://economictimes.indiatimes.com/small-biz/rssfeeds/1977021501.cms',
    'et_now':              'https://economictimes.indiatimes.com/et-now/rssfeeds/1977021501.cms',
    'sports':              'https://economictimes.indiatimes.com/sports/rssfeeds/1977021501.cms',
}
Import ET_FEEDS from config inside scrapers/economictimes.py (do not hardcode URLs in the scraper).
Task 4 — Update main.py
Import the new scraper at the top:
pythonfrom scrapers.economictimes import scrape_et
Add ET to the existing slow scrape loop. The existing code has a while True loop that calls scrapers and sleeps. Find the section where scrape_aljazeera(), scrape_reuters(), scrape_moneycontrol() are called and add ET there:
python# Inside slow_scrape_loop() or equivalent
try:
    articles = scrape_et()
    for art in articles:
        msid = get_msid(art['url'])
        article_id = f"ET_{msid}" if msid else art['url']
        if is_new(article_id):
            save_article(art)
            mark_seen(article_id)
            notify_new_article(art)
            logging.info(f"[ET] New article: {art['title']}")
except Exception as e:
    logging.error(f"ET poll error: {e}")
The ET scraper imports get_msid internally — expose it from scrapers/economictimes.py so main.py can use it. Alternatively, let the scraper return article_id as part of the dict itself (add 'article_id': f"ET_{msid}" to the dict inside scrape_et() and use art['article_id'] in main.py).
Poll interval: ET runs in the same slow loop as MoneyControl. The loop sleeps ET_POLL_INTERVAL (60s) between full-cycle runs.
Important — cross-feed dedup within ET: Because the same article can appear in markets, stocks, AND top_stories, the msid-based dedup key ("ET_" + msid) ensures each article is only ever saved once regardless of which feed it came from first.
Task 5 — Update dashboard/app.py
Add ET-specific API endpoints and update grouped endpoint:
pythonfrom scrapers.economictimes import FEEDS as ET_FEEDS
@app.route('/api/news/et')
def api_et_news():
    """All ET articles, newest first, limit 100"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM articles WHERE source='Economic Times' ORDER BY scraped_at DESC LIMIT 100"
    ).fetchall()
    return jsonify([dict(r) for r in rows])
@app.route('/api/news/et/<category>')
def api_et_category(category):
    """ET articles filtered by category, limit 50"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM articles WHERE source='Economic Times' AND category=? ORDER BY scraped_at DESC LIMIT 50",
        (category,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])
@app.route('/api/news/et/categories')
def api_et_categories():
    """List of distinct categories found in DB for ET"""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT category, COUNT(*) as count FROM articles WHERE source='Economic Times' GROUP BY category ORDER BY count DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])
Update /api/news/grouped to include ET:
python# Add to the grouped response dict:
'et': [dict(r) for r in db.execute(
    "SELECT * FROM articles WHERE source='Economic Times' ORDER BY scraped_at DESC LIMIT 30"
).fetchall()]
```
---
## Task 6 — Update `dashboard/templates/index.html`
**ET section in the dashboard layout:**
Add an "Economic Times" panel. The recommended layout with all 5 sources is:
```
Row 1 (full width): ScanX News Flash (live 15s feed)
Row 2 (3-column):   Al Jazeera | Reuters | Economic Times
Row 3 (2-column):   MoneyControl | [ET Markets sub-section]
For the ET panel specifically:

Header: "Economic Times" with a category dropdown or tab strip showing: top_stories | markets | stocks | news_politics | news_defence | tech | wealth
On tab click: fetch /api/news/et/{category} and re-render the articles list
Default tab: top_stories
Each article card: title (as clickable link), category badge, pubDate or scraped_at as relative time
Auto-refresh: every 60 seconds, re-fetch the active tab's category endpoint
JavaScript for the ET panel:

javascriptlet etActiveCategory = 'top_stories';
function loadEtNews(category) {
    etActiveCategory = category;
    fetch(`/api/news/et/${category}`)
        .then(r => r.json())
        .then(articles => renderEtPanel(articles));
}
function renderEtPanel(articles) {
    const container = document.getElementById('et-articles');
    container.innerHTML = articles.map(a => `
        <div class="article-card">
            <a href="${a.url}" target="_blank">${a.title}</a>
            <span class="badge">${a.category}</span>
            <span class="time">${a.scraped_at}</span>
        </div>
    `).join('');
}
setInterval(() => loadEtNews(etActiveCategory), 60000);
loadEtNews('top_stories');

Task 7 — Update scrapers/__init__.py
Add the new import so all scrapers are accessible from the package:
pythonfrom .economictimes import scrape_et
```
---
## Task 8 — Update `requirements.txt`
Ensure these are present (feedparser and beautifulsoup4 should already be there from the existing codebase):
```
feedparser>=6.0
beautifulsoup4>=4.12
lxml>=4.9        # faster HTML parser for BS4, improves description parsing
lxml is recommended because the description field in ET RSS contains HTML that BeautifulSoup needs to parse — lxml is 3–5x faster than the default html.parser for this.
Critical Notes for Claude Code
User-Agent is mandatory. ET's CDN returns HTTP 403 to the default Python feedparser User-Agent. The request_headers param in feedparser.parse() must always be set:
pythonHEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
feed = feedparser.parse(url, request_headers=HEADERS)
Cross-feed duplicate suppression is handled entirely by the msid-based article_id. The same article appearing in both markets and stocks feeds will have the same msid → same article_id → is_new() returns False on the second occurrence → silently skipped. No extra set/cache needed.
ET RSS item count: Each feed returns exactly 10 items at a time (confirmed from live data above). With 25 feeds × 10 items = up to 250 items per poll cycle — but dedup will collapse most of the cross-feed overlap. Net new articles per 60-second cycle will typically be 5–25 in fast-moving market hours.
pubDate format: "Mon, 09 Mar 2026 11:33:03 +0530" — standard RFC 2822. feedparser automatically parses this into a time.struct_time at entry.published_parsed. Use time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed) for consistent DB storage. The raw string from entry.published can also be stored as-is.
The rssfeedstopstories.cms feed quirk: This named feed returns articles from across all sections (confirmed: mix of wealth, markets, news/defence, industry articles in the live data), but with no description or thumbnail. Poll it for the broadest cross-section coverage, but the section-specific feeds are better for rich content. Run both — the msid dedup ensures no duplicates.