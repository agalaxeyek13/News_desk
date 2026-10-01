"""
Entity + relationship extraction — the "connect the news" step.

One local-LLM call per article pulls out both the entities it's about
(people, orgs, locations, weapon systems, event type) AND the actual
subject-relation-object relationships between them (e.g. "IRGC" ->
"launched strikes on" -> "oil tanker"). linker.py clusters same-day
articles that share entities into story threads; the relationships are
what let composer.py describe *how* those entities connect instead of
just that they co-occur, and let it ground the written synthesis in
extracted facts rather than raw excerpts alone.
"""

import json
import logging

from fde.llm import chat

logger = logging.getLogger(__name__)

_EMPTY = {
    "people": [],
    "orgs": [],
    "locations": [],
    "weapon_systems": [],
    "event_type": "",
    "relationships": [],
}

_SYSTEM_PROMPT = """You extract structured entities AND relationships from a single news article \
for a US-Iran defense/geopolitics monitoring pipeline. Respond with ONLY a JSON object, no prose, \
no markdown fences, matching exactly this shape:

{"people": [], "orgs": [], "locations": [], "weapon_systems": [], "event_type": "", "relationships": []}

Rules:
- "people": named individuals mentioned (full names as written in the text).
- "orgs": organizations, agencies, military units, or companies (e.g. "IRGC", "US Navy", "Lockheed Martin").
- "locations": places relevant to the event (e.g. "Strait of Hormuz", "Tehran").
- "weapon_systems": named weapons, platforms, or equipment if any are mentioned (e.g. "F-35", "Shahed drone"); empty list if none.
- "event_type": a short lowercase phrase for what kind of event this is (e.g. "military movement", "contract award", "diplomatic statement", "analysis").
- "relationships": a list of objects {"subject": "", "relation": "", "object": ""} capturing WHO did WHAT to WHOM, \
using only entities that also appear in people/orgs/locations/weapon_systems above. The "relation" is a short verb \
phrase taken from what the article actually states (e.g. "launched strikes on", "awarded contract to", "met with", \
"deployed to"). Only include a relationship the text directly supports — never infer or guess one. Empty list if none.
- If a field has no values, use an empty list (or empty string for event_type). Never omit a key.
"""


def _parse_json(raw: str) -> dict:
    """Strip markdown fences if the model added them, then parse."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _clean_relationships(relationships) -> list:
    """Keep only well-formed {subject, relation, object} triples."""
    cleaned = []
    if not isinstance(relationships, list):
        return cleaned
    for r in relationships:
        if not isinstance(r, dict):
            continue
        subject, relation, obj = r.get("subject"), r.get("relation"), r.get("object")
        if subject and relation and obj:
            cleaned.append({"subject": str(subject), "relation": str(relation), "object": str(obj)})
    return cleaned


def extract(article: dict) -> dict:
    """
    Extract entities and relationships from one article. Returns the shape
    in _EMPTY (populated where possible), or an all-empty dict on any
    failure — a single bad extraction should not break the whole run.
    """
    text = f"{article.get('title', '')}\n\n{article.get('content', '')}".strip()[:4000]
    if not text:
        return dict(_EMPTY)

    raw = chat(_SYSTEM_PROMPT, text, max_tokens=600)
    if not raw:
        return dict(_EMPTY)

    try:
        parsed = _parse_json(raw)
        for key, default in _EMPTY.items():
            parsed.setdefault(key, default)
        parsed["relationships"] = _clean_relationships(parsed["relationships"])
        return parsed
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        logger.warning("Entity extraction returned unparseable output: %s", e)
        return dict(_EMPTY)
