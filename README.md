# 📰 News Alert System

A production-grade, near-real-time news monitoring dashboard that tracks Al Jazeera and Reuters, with special support for Al Jazeera **liveblogs** via direct GraphQL API polling (latency ~15 seconds).

## Features

- **Real-time liveblog tracking** — polls Al Jazeera's GraphQL API every 15s for liveblog updates
- **Auto-discovery** — automatically finds active liveblogs from the AJ homepage and breaking ticker
- **Al Jazeera RSS + HTML** — full article feed via RSS with homepage HTML fallback
- **Reuters** — multi-category feed via Google News RSS proxy
- **Live dashboard** — 3-column responsive web UI with 10s auto-refresh LIVE section
- **Filter bar** — filter by All / Al Jazeera / Reuters / 🔴 Live
- **Desktop notifications** — via plyer (optional)
- **Thread-safe SQLite storage** — dual poll loops writing concurrently

## Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and edit as needed:

```bash
cp .env.example .env
```

To manually track a specific liveblog, add its slug to `TRACKED_LIVEBLOG_SLUGS` in `config.py`:

```python
TRACKED_LIVEBLOG_SLUGS = ["iran-war-live-mojtaba-khamenei-named-supreme-leader-israel-bombs-tehran"]
```

Or let auto-discovery handle it — it checks every 5 minutes.

## Running

```bash
python main.py
```

Open **http://localhost:5050** in your browser.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   main.py                        │
│                                                  │
│  ┌──────────────────┐  ┌────────────────────┐   │
│  │  Slow Loop (120s) │  │ Fast Loop (15s)    │   │
│  │  aljazeera.scrape │  │ liveblog.scrape    │   │
│  │  reuters.scrape   │  │ liveblog_discovery │   │
│  └────────┬─────────┘  └────────┬───────────┘   │
│           └──────────┬──────────┘               │
│                      ▼                           │
│              storage/db.py (SQLite + Lock)       │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
           dashboard/app.py (Flask)
                      │
                      ▼
          http://localhost:5050
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/news` | All recent articles |
| `GET /api/news/grouped` | Grouped by source |
| `GET /api/news/live` | Liveblog updates only |
| `GET /api/status` | System health/status |
