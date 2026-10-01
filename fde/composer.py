"""
Renders scored clusters into the FDE Briefing HTML email.

Table-based markup with inline styles throughout — Outlook renders HTML
email with Word's engine, which doesn't support flexbox/grid, so this is
deliberately NOT built the way the browser mockup was.
"""

import logging
import re
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fde.llm import chat
from fde.domains import classify, DOMAIN_COLORS, DEFAULT_DOMAIN
from fde.filter import is_opinion
from config import (
    FDE_TEAM_NAME, FDE_RECENCY_HOURS,
    FDE_DISPLAY_TZ_OFFSET_MINUTES, FDE_DISPLAY_TZ_LABEL,
)

logger = logging.getLogger(__name__)

TOP_N = 8  # full written sections; everything else is listed by source below

_DISPLAY_TZ = timezone(timedelta(minutes=FDE_DISPLAY_TZ_OFFSET_MINUTES))
_PUBLISHED_FORMAT = "%Y-%m-%d %H:%M:%S"
_SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif"
_SERIF = "Georgia,'Times New Roman',serif"

# Sources whose links are redirects (Google News) — show the outlet's own domain.
_SOURCE_DOMAINS = {"Reuters": "reuters.com"}


_SYNTHESIS_SYSTEM_PROMPT = """You write one short paragraph (3-4 sentences) for an internal defense-industry \
briefing, synthesizing the article excerpts you're given into a single neutral, factual account of the story \
thread they share. Rules:
- The excerpt marked [LEAD] is the story this paragraph is about. Open with it, and bring in the other \
excerpts only where they add to that same story. The paragraph sits directly under the LEAD article's \
headline, so it must not read as if it is about a different story.
- Only state what the excerpts support. Do not invent facts, quotes, or figures.
- No editorializing, no speculation beyond what a source explicitly says.
- Plain prose, no headline, no bullet points, no source citations inline (sources are listed separately).
- Write only the paragraph. Never mention the excerpts, the sources, or what information you were given.
"""


def _relationships_block(cluster: dict) -> str:
    """Render the cluster's extracted relationship triples as plain lines,
    given to the model as grounding facts alongside the raw excerpts."""
    triples = cluster.get("relationships") or []
    if not triples:
        return ""
    lines = "\n".join(f"- {r['subject']} {r['relation']} {r['object']}" for r in triples[:10])
    return f"\n\nExtracted facts (subject / relation / object), only state what these and the excerpts support:\n{lines}"


_MIN_CONTENT_CHARS = 150  # below this (even after enrichment) there's not enough text for a real section
# Phrasings where the model talks about the prompt instead of the news.
# Any of these anywhere in the output means it isn't briefing copy.
_REFUSAL_MARKERS = (
    "please provide", "i cannot fulfill", "i don't have", "i do not have",
    "no excerpts", "no article", "excerpts do not", "the provided excerpts",
    "excerpts you provided", "as an ai",
)


_MIN_USABLE_BODY_CHARS = 80


def _strip_meta_sentences(text: str) -> str:
    """Drop sentences where the model talks about the prompt rather than the
    news, keeping the rest. It often writes a good paragraph and then tacks
    on "The provided excerpts do not specify..." — discarding the whole
    output over that trailing sentence throws away real briefing copy."""
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in sentences if not any(m in s.lower() for m in _REFUSAL_MARKERS)]
    cleaned = " ".join(kept).strip()
    return cleaned if len(cleaned) >= _MIN_USABLE_BODY_CHARS else ""


def has_enough_content(cluster: dict) -> bool:
    """True if this cluster has enough scraped text to earn a full section
    (with a written synthesis) rather than being a one-line Also Noted item."""
    return sum(len(a.get("content", "")) for a in cluster["articles"]) >= _MIN_CONTENT_CHARS


def _synthesize(cluster: dict) -> str:
    """One local-LLM call: turn a cluster's articles into a short synthesis paragraph."""
    excerpts = "\n\n".join(
        f"[{'LEAD' if i == 0 else 'SUPPORTING'} — {a['source']}] {a['title']}\n{a.get('content', '')[:1200]}"
        for i, a in enumerate(cluster["articles"][:6])
    )
    result = chat(_SYNTHESIS_SYSTEM_PROMPT, excerpts + _relationships_block(cluster), max_tokens=350)
    return _strip_meta_sentences(result)


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _site_domain(article: dict) -> str:
    if article.get("source") in _SOURCE_DOMAINS:
        return _SOURCE_DOMAINS[article["source"]]
    host = urlparse(article.get("url", "")).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _parse_published(article: dict):
    try:
        return datetime.strptime(article.get("published", ""), _PUBLISHED_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _local(dt: datetime) -> str:
    return dt.astimezone(_DISPLAY_TZ).strftime("%d %b, %H:%M ") + FDE_DISPLAY_TZ_LABEL


def _time_label(article: dict) -> str:
    dt = _parse_published(article)
    if dt is None:
        return "time unknown"
    if article.get("live"):
        return "Live blog &middot; opened " + dt.strftime("%d %b")
    return _local(dt)


def _newest_first(articles: list) -> list:
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(articles, key=lambda a: _parse_published(a) or epoch, reverse=True)


def _link(url: str, text: str, style: str = "color:#141413;text-decoration:none;") -> str:
    return f'<a href="{_escape(url)}" style="{style}">{text}</a>'


def _meta_line(article: dict) -> str:
    """'domain · 01 Oct, 17:26 IST' under a headline."""
    return f"{_escape(_site_domain(article))} &middot; {_time_label(article)}"


def _sources_html(cluster: dict) -> str:
    """Every article in the thread: outlet (linked) · domain · publish time."""
    rows = "".join(
        f'<div style="margin-top:3px;">'
        f'{_link(a["url"], _escape(a["source"]), "color:#141413;text-decoration:underline;")}'
        f' &middot; {_meta_line(a)}</div>'
        for a in cluster["articles"]
    )
    return (
        f'<div style="font-family:{_SANS};font-size:11.5px;color:#6b6b68;">'
        f'<span style="font-weight:700;color:#8a8a86;">SOURCES</span>{rows}</div>'
    )


def _extractive_fallback(cluster: dict) -> str:
    """Last-resort body text if the model returned nothing usable despite
    having enough source text — pulls straight from the article itself,
    no LLM, so it's always something real rather than an apology."""
    content = cluster["articles"][0].get("content", "")
    snippet = content[:400]
    last_period = snippet.rfind(". ")
    return snippet[:last_period + 1] if last_period > 100 else snippet


_PLACEHOLDER_IMAGE_USES = 3  # one image on this many articles is a site default, not a photo


def _image_key(url: str) -> str:
    return url.split("?", 1)[0]  # the query string is only resize/cache parameters


def _dedupe_thumbnails(sections: list, listed: list) -> None:
    """Never show the same picture twice in one email.

    An image carried by several articles is a site placeholder (every
    Middle East Eye live-blog update has the blog's cover image) and is
    dropped everywhere. Otherwise the first use in email order keeps it:
    each section shows the first of its articles with a still-unused
    image, then the listing rows in the order they're rendered."""
    everyone = [a for c in sections for a in c["articles"]] + listed
    uses = {}
    for a in everyone:
        if a.get("thumbnail"):
            uses[_image_key(a["thumbnail"])] = uses.get(_image_key(a["thumbnail"]), 0) + 1

    shown = set()

    def claim(article) -> bool:
        k = _image_key(article.get("thumbnail") or "")
        if not k or uses[k] >= _PLACEHOLDER_IMAGE_USES or k in shown:
            article["thumbnail"] = ""
            return False
        shown.add(k)
        return True

    for cluster in sections:
        for i, article in enumerate(cluster["articles"]):
            if claim(article):
                # The section renders this one; the rest of its articles show no image.
                for other in cluster["articles"][i + 1:]:
                    other["thumbnail"] = ""
                break
    for article in listed:
        claim(article)


def _thumbnail_html(cluster: dict) -> str:
    """First available thumbnail across the thread, linked to its article.
    Outlook blocks external images by default until the recipient clicks
    'Download pictures' — that's an Outlook setting, not something this
    code can override."""
    article = next((a for a in cluster["articles"] if a.get("thumbnail")), None)
    if not article:
        return ""
    img = (
        f'<img src="{_escape(article["thumbnail"])}" alt="" width="544" '
        f'style="width:544px;max-width:544px;height:auto;display:block;margin:10px 0;border:1px solid #e2e2df;">'
    )
    return _link(article["url"], img)


def _tag_label(cluster: dict) -> str:
    """Pick a short label from the cluster's extracted entities — the first
    location if any, else the first article's event_type, else nothing."""
    for article in cluster["articles"]:
        entities = article.get("_entities") or {}
        if entities.get("locations"):
            return entities["locations"][0]
    for article in cluster["articles"]:
        event_type = (article.get("_entities") or {}).get("event_type")
        if event_type:
            return event_type.title()
    return ""


def _connections_html(cluster: dict) -> str:
    """Small 'Key connections' line rendering up to 3 relationship triples
    as Subject -> relation -> Object — the visible graph behind the story."""
    triples = cluster.get("relationships") or []
    if not triples:
        return ""
    items = " &nbsp;&middot;&nbsp; ".join(
        f'{_escape(r["subject"])} <span style="color:#b8956a;">&rarr;</span> {_escape(r["relation"])} '
        f'<span style="color:#b8956a;">&rarr;</span> {_escape(r["object"])}'
        for r in triples[:3]
    )
    return (
        f'<div style="font-family:{_SANS};font-size:11px;'
        f'font-style:italic;color:#8a8a86;margin-top:6px;">{items}</div>'
    )


def _section_html(cluster: dict) -> str:
    domain = cluster["domain"]
    bg, fg = DOMAIN_COLORS.get(domain, DOMAIN_COLORS[DEFAULT_DOMAIN])
    lead = cluster["articles"][0]
    body = cluster.get("synthesis") or _extractive_fallback(cluster)
    return f"""
    <tr><td style="padding: 22px 28px; border-bottom: 1px solid #e2e2df; font-family: {_SERIF};">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background: {bg}; color: {fg}; font-family: {_SANS}; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; padding: 3px 8px; border-radius: 3px;">{domain}</td>
        <td style="width: 8px;"></td>
        <td style="color: #8a8a86; font-family: {_SANS}; font-size: 11px;">{_escape(_tag_label(cluster))}</td>
      </tr></table>
      <div style="height: 10px;"></div>
      <div style="font-size: 21px; font-weight: 700; line-height: 1.3;">{_link(lead["url"], _escape(lead["title"]))}</div>
      <div style="font-family: {_SANS}; font-size: 11px; color: #8a8a86; margin-top: 4px;">{_meta_line(lead)}</div>
      {_connections_html(cluster)}
      {_thumbnail_html(cluster)}
      <div style="height: 8px;"></div>
      <div style="font-size: 14.5px; line-height: 1.6; color: #3a3a38;">{_escape(body)}</div>
      <div style="height: 12px;"></div>
      {_sources_html(cluster)}
    </td></tr>
    """


def _listing_row(article: dict) -> str:
    thumb = ""
    if article.get("thumbnail"):
        img = (
            f'<img src="{_escape(article["thumbnail"])}" alt="" width="84" '
            f'style="width:84px;height:auto;display:block;border:1px solid #e2e2df;">'
        )
        thumb = _link(article["url"], img)
    return f"""
      <tr>
        <td width="96" valign="top" style="width:96px;padding:0 12px 14px 0;">{thumb}</td>
        <td valign="top" style="padding:0 0 14px;">
          <div style="font-family:{_SERIF};font-size:14px;line-height:1.4;font-weight:700;">{_link(article["url"], _escape(article["title"]))}</div>
          <div style="font-family:{_SANS};font-size:11px;color:#8a8a86;margin-top:3px;">{_meta_line(article)}</div>
        </td>
      </tr>"""


def _listing_block(title: str, articles: list) -> str:
    """Headlines grouped by outlet, newest first, each with image, domain and time."""
    if not articles:
        return ""
    by_source = OrderedDict()
    for article in _newest_first(articles):
        by_source.setdefault(article["source"], []).append(article)

    groups = ""
    for source, items in sorted(by_source.items(), key=lambda kv: kv[0].lower()):
        rows = "".join(_listing_row(a) for a in items)
        groups += f"""
      <div style="font-family:{_SANS};font-size:12px;font-weight:700;color:#141413;margin:14px 0 8px;">
        {_escape(source)} <span style="font-weight:400;color:#8a8a86;">&middot; {_escape(_site_domain(items[0]))} &middot; {len(items)}</span>
      </div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>"""

    return f"""
    <tr><td style="padding: 20px 28px 6px; border-bottom: 1px solid #e2e2df;">
      <div style="font-family:{_SANS};font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#8a8a86;font-weight:700;">{title} ({len(articles)})</div>
      {groups}
    </td></tr>
    """


def compose_email(clusters: list, listing: list = None) -> tuple:
    """
    Give a full written section to every cluster that has enough source
    text to synthesize honestly (up to TOP_N). Every other article from the
    window — thin or overflow clusters, plus `listing` (non-Iran items from
    the defense/regional outlets, opinion pieces) — is listed by outlet
    below, each with its image, domain and publish time.
    Returns (subject, html_body).
    """
    content_rich = [c for c in clusters if has_enough_content(c)]
    top = content_rich[:TOP_N]
    top_ids = {id(c) for c in top}

    remaining = [a for c in clusters if id(c) not in top_ids for a in c["articles"]]
    remaining += listing or []
    opinion = [a for a in remaining if is_opinion(a)]
    news = [a for a in remaining if not is_opinion(a)]

    def listing_order(items):
        return sorted(_newest_first(items), key=lambda a: a["source"].lower())

    _dedupe_thumbnails(top, listing_order(news) + listing_order(opinion))

    for cluster in top:
        cluster["domain"] = classify(cluster)
        cluster["synthesis"] = _synthesize(cluster)

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=FDE_RECENCY_HOURS)
    today_str = now.astimezone(_DISPLAY_TZ).strftime("%A, %B %d, %Y")

    domain_counts = OrderedDict()
    for c in top:
        domain_counts[c["domain"]] = domain_counts.get(c["domain"], 0) + 1
    domains_line = " &middot; ".join(f"{k.title()} {v}" for k, v in domain_counts.items())
    sources = {a["source"] for c in clusters for a in c["articles"]} | {a["source"] for a in listing or []}
    brief_line = (
        f"{len(top)} stories in detail, {len(news)} more headlines and {len(opinion)} opinion pieces "
        f"from {len(sources)} outlets, published {_local(window_start)} &ndash; {_local(now)}."
    )

    sections = "".join(_section_html(c) for c in top)
    listed = _listing_block("More from the last 24 hours", news) + _listing_block("Opinion &amp; Commentary", opinion)

    html = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="margin:0;background:#e8e8e6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#e8e8e6;">
<tr><td align="center" style="padding: 24px 0;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border:1px solid #d8d8d4;">

<tr><td style="background:#141413;padding:22px 28px 18px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td style="color:#ffffff;font-family:{_SERIF};font-size:22px;font-weight:700;letter-spacing:0.5px;">{_escape(FDE_TEAM_NAME)} BRIEFING</td>
    <td align="right" style="color:#a8a8a4;font-family:{_SANS};font-size:10px;letter-spacing:1px;text-transform:uppercase;">Internal Distribution</td>
  </tr>
  <tr>
    <td style="color:#a8a8a4;font-family:{_SANS};font-size:11px;">US&ndash;Iran Watch &middot; Daily</td>
    <td align="right" style="color:#a8a8a4;font-family:{_SANS};font-size:11px;">{today_str}</td>
  </tr>
  </table>
</td></tr>

<tr><td style="padding:22px 28px 18px;border-bottom:1px solid #e2e2df;">
  <div style="font-family:{_SANS};font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#8a1f1f;font-weight:700;margin-bottom:8px;">Today in Brief</div>
  <div style="font-family:{_SERIF};font-size:15.5px;line-height:1.55;color:#141413;">{brief_line}</div>
  <div style="font-family:{_SANS};font-size:11px;color:#8a8a86;margin-top:6px;">{domains_line}</div>
</td></tr>

{sections}
{listed}

<tr><td style="padding:16px 28px 24px;color:#9a9a96;font-family:{_SANS};font-size:10.5px;line-height:1.6;">
  Compiled automatically from the open-source reporting linked above. Times are publish times in {FDE_DISPLAY_TZ_LABEL}. Verify independently before acting on any item. Internal distribution only &mdash; do not forward externally.
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    subject = f"{FDE_TEAM_NAME} Briefing — {today_str}"
    return subject, html
