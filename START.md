# FDE Briefing — how to run it

Daily US-Iran defense briefing, emailed to the FDE team. Scrapes ~12 sources,
groups the articles into story threads with a local GPU model, writes the
briefing, and sends it through the Outlook app on this machine.

## Run it

```powershell
cd C:\Users\Galaxeye\Documents\GitHub\News_desk
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
python -m fde.run_daily
```

Takes ~2-3 minutes. Runs once and exits — it is not a background service.

**Before running:** Outlook desktop must be open and signed in. The briefing is
sent through that live session, so there is no SMTP password or API key to set.
The first send in a session may raise an Outlook prompt asking to allow a
program to send mail — click **Allow** (not Close, or the send is aborted).

`KMP_DUPLICATE_LIB_OK` is required because Anaconda's MKL and PyTorch both ship
an OpenMP runtime and the process aborts on startup without it. It only applies
to that PowerShell window; set it permanently under System Properties →
Environment Variables to stop repeating it.

## Change who gets it

Edit `FDE_RECIPIENTS` in `.env` (comma-separated for several people):

```
FDE_RECIPIENTS=someone@galaxeye.space,someone.else@galaxeye.space
```

## Common tweaks

| Setting | Where | Now |
|---|---|---|
| Sources (RSS feeds) | `config.py` → `FDE_RSS_FEEDS` | 12 feeds |
| Topic keywords | `config.py` → `FDE_KEYWORDS` | Iran + proxies + theater |
| How far back to look | `config.py` → `FDE_RECENCY_HOURS` | 48 hours |
| Full sections in the email | `fde/composer.py` → `TOP_N` | 8 |
| Model file | `config.py` → `FDE_LOCAL_MODEL_PATH` | Gemma 26B GGUF |

## What runs, in order

`fde/run_daily.py` calls, in sequence:

1. `scrapers/` (Al Jazeera, Reuters) + `fde/scrapers/` (12 RSS feeds, ISW) — scrape
2. `fde/filter.py` — drop anything older than 48h or not US-Iran related
3. `fde/store.py` — drop anything already sent in a previous briefing
4. `fde/enrich.py` — fetch each article's real page text and image
5. `fde/extractor.py` — local LLM pulls entities + relationships per article
6. `fde/linker.py` — group articles into story threads
7. `fde/scorer.py` — rank threads, tag ESCALATING / STEADY / DEVELOPING
8. `fde/composer.py` — write each thread's paragraph, build the HTML email
9. `fde/mailer.py` — send via Outlook

## Where the data is

Everything is in `news.db` in this folder (shared with the dashboard, separate
tables):

- `fde_sent_articles` — already-briefed URLs, so stories do not repeat
- `fde_cluster_history` — daily thread snapshots; this is what makes the
  ESCALATING / STEADY tags work, so it needs a few consecutive days of runs
  before those tags mean anything

## If something goes wrong

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: No module named 'http.client'` | `KMP_DUPLICATE_LIB_OK` / env issue — see above |
| `Operation aborted` from the mailer | The Outlook allow-prompt was closed instead of allowed |
| "No new relevant articles today — skipping send" | Everything in the window was already briefed; normal on a quiet day |
| A feed logs `mismatched tag` | That source served malformed XML this run; it is skipped and the rest continues |

Reuters and Times of Israel articles stay headline-only — Reuters comes via a
Google News redirect that cannot be fetched, and Times of Israel returns 403 to
the enrichment fetch.
