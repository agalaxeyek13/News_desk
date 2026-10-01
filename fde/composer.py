"""
Renders scored clusters into the FDE Briefing HTML email.

Table-based markup with inline styles throughout — Outlook renders HTML
email with Word's engine, which doesn't support flexbox/grid, so this is
deliberately NOT built the way the browser mockup was.
"""

import logging
import re
from datetime import date

from fde.llm import chat
from config import FDE_TEAM_NAME

logger = logging.getLogger(__name__)

_TREND_COLORS = {
    "ESCALATING": ("#f4dede", "#8a1f1f"),
    "STEADY":     ("#eceae4", "#6b6b68"),
    "DEVELOPING": ("#f6ead2", "#8a5a12"),
}

TOP_N = 8        # full written sections
ALSO_NOTED_N = 12  # one-line links for everything else that cleared the gate


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
    )


def _sources_line(cluster: dict) -> str:
    seen = {}
    for a in cluster["articles"]:
        seen.setdefault(a["source"], a["url"])
    links = " &middot; ".join(
        f'<a href="{_escape(url)}" style="color:#141413;text-decoration:underline;">{_escape(src)}</a>'
        for src, url in seen.items()
    )
    return links


def _extractive_fallback(cluster: dict) -> str:
    """Last-resort body text if the model returned nothing usable despite
    having enough source text — pulls straight from the article itself,
    no LLM, so it's always something real rather than an apology."""
    content = cluster["articles"][0].get("content", "")
    snippet = content[:400]
    last_period = snippet.rfind(". ")
    return snippet[:last_period + 1] if last_period > 100 else snippet


def _thumbnail_html(cluster: dict) -> str:
    """First available thumbnail image across the cluster's articles, if any.
    Outlook blocks external images by default until the recipient clicks
    'Download pictures' — that's an Outlook setting, not something this
    code can override."""
    thumbnail = next((a.get("thumbnail") for a in cluster["articles"] if a.get("thumbnail")), None)
    if not thumbnail:
        return ""
    return (
        f'<img src="{_escape(thumbnail)}" alt="" width="544" '
        f'style="width:544px;max-width:544px;height:auto;display:block;margin:10px 0;border:1px solid #e2e2df;">'
    )


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
        f'<div style="font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;font-size:11px;'
        f'font-style:italic;color:#8a8a86;margin-top:6px;">{items}</div>'
    )


def _section_html(cluster: dict) -> str:
    bg, fg = _TREND_COLORS.get(cluster["trend"], _TREND_COLORS["STEADY"])
    tag_label = _tag_label(cluster)
    headline = cluster["articles"][0]["title"]
    body = cluster.get("synthesis") or _extractive_fallback(cluster)
    connections = _connections_html(cluster)
    thumbnail = _thumbnail_html(cluster)
    return f"""
    <tr><td style="padding: 22px 28px; border-bottom: 1px solid #e2e2df; font-family: Georgia, 'Times New Roman', serif;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background: {bg}; color: {fg}; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; padding: 3px 8px; border-radius: 3px;">{cluster['trend']}</td>
        <td style="width: 8px;"></td>
        <td style="color: #8a8a86; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11px;">{tag_label}</td>
      </tr></table>
      <div style="height: 10px;"></div>
      <div style="font-size: 21px; font-weight: 700; line-height: 1.3; color: #141413;">{_escape(headline)}</div>
      {connections}
      {thumbnail}
      <div style="height: 8px;"></div>
      <div style="font-size: 14.5px; line-height: 1.6; color: #3a3a38;">{_escape(body)}</div>
      <div style="height: 10px;"></div>
      <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11.5px; color: #6b6b68;">Sources: {_sources_line(cluster)}</div>
    </td></tr>
    """


def _also_noted_html(clusters: list) -> str:
    if not clusters:
        return ""
    rows = ""
    for cluster in clusters[:ALSO_NOTED_N]:
        article = cluster["articles"][0]
        rows += (
            f'<div style="font-size: 13.5px; line-height: 1.5; color: #3a3a38; '
            f'font-family: Georgia, \'Times New Roman\', serif; margin-bottom: 10px;">'
            f'{_escape(article["title"])} — '
            f'<a href="{_escape(article["url"])}" style="color:#141413;">{_escape(article["source"])} &rarr;</a>'
            f'</div>'
        )
    return f"""
    <tr><td style="padding: 20px 28px 6px;">
      <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #8a8a86; font-weight: 700; margin-bottom: 12px;">Also Noted</div>
      {rows}
    </td></tr>
    """


def compose_email(clusters: list) -> tuple:
    """
    Give a full written section to every cluster that has enough source
    text to synthesize honestly (up to TOP_N), and demote the rest —
    genuinely thin ones, or overflow beyond TOP_N — to one-line "Also
    Noted" links instead of padding out a section with an apology.
    Returns (subject, html_body).
    """
    content_rich = [c for c in clusters if has_enough_content(c)]
    thin = [c for c in clusters if not has_enough_content(c)]

    top = content_rich[:TOP_N]
    rest = content_rich[TOP_N:] + thin

    for cluster in top:
        cluster["synthesis"] = _synthesize(cluster)

    today_str = date.today().strftime("%A, %B %d, %Y")

    sections = "".join(_section_html(c) for c in top)
    also_noted = _also_noted_html(rest)

    lead_trend_counts = {}
    for c in top:
        lead_trend_counts[c["trend"]] = lead_trend_counts.get(c["trend"], 0) + 1
    brief_line = ", ".join(f"{v} {k.lower()}" for k, v in lead_trend_counts.items()) or "no active threads"

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
    <td style="color:#ffffff;font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:700;letter-spacing:0.5px;">{_escape(FDE_TEAM_NAME)} BRIEFING</td>
    <td align="right" style="color:#a8a8a4;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;">Internal Distribution</td>
  </tr>
  <tr>
    <td style="color:#a8a8a4;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:11px;">US&ndash;Iran Watch &middot; Daily</td>
    <td align="right" style="color:#a8a8a4;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:11px;">{today_str}</td>
  </tr>
  </table>
</td></tr>

<tr><td style="padding:22px 28px 18px;border-bottom:1px solid #e2e2df;">
  <div style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#8a1f1f;font-weight:700;margin-bottom:8px;">Today in Brief</div>
  <div style="font-family:Georgia,'Times New Roman',serif;font-size:15.5px;line-height:1.55;color:#141413;">{len(clusters)} US-Iran story thread(s) tracked today ({brief_line}).</div>
</td></tr>

{sections}
{also_noted}

<tr><td style="padding:16px 28px 24px;border-top:1px solid #e2e2df;color:#9a9a96;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:10.5px;line-height:1.6;">
  Compiled automatically from the open-source reporting linked above. Verify independently before acting on any item. Internal distribution only &mdash; do not forward externally.
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    subject = f"{FDE_TEAM_NAME} Briefing — {today_str}"
    return subject, html
