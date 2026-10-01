"""
Operational domain of a story thread (Maritime, Air, Nuclear, ...), shown
as the badge on each briefing section.

Keyword scoring rather than an LLM call: it's deterministic, free, and a
headline hit is a strong enough signal. Headline matches count three times
a body match, so a story is labelled by what it's about rather than by
something its body mentions in passing.
"""

import re

DOMAINS = {
    "MARITIME":     ["hormuz", "tanker", "navy", "naval", "vessel", "ship", "shipping", "strait",
                     "red sea", "bab al-mandeb", "fleet", "maritime", "seized"],
    "AIR":          ["airspace", "aircraft", "fighter", "jet", "f-35", "f-16", "air force", "airbase",
                     "air base", "bomber", "flight", "aviation", "raf ", "airstrike"],
    "MISSILE":      ["missile", "ballistic", "drone", "uav", "rocket", "projectile", "interceptor",
                     "air defense", "air defence"],
    "NUCLEAR":      ["nuclear", "uranium", "enrichment", "iaea", "natanz", "fordow", "centrifuge"],
    "LAND":         ["troops", "ground", "militia", "withdrawal", "border", "army", "brigade",
                     "soldiers", "kurdish forces", "peshmerga"],
    "CYBER":        ["cyber", "hack", "malware", "ransomware"],
    "SPACE":        ["satellite", "space", "orbit", "launch vehicle"],
    "SECURITY":     ["plot", "terror", "arrest", "intelligence", "spy", "espionage", "attack on",
                     "foiled", "assassination"],
    "DIPLOMATIC":   ["talks", "dialogue", "proposal", "negotiat", "sanction", "ceasefire", "envoy",
                     "minister", "president says", "summit", "deal", "un security council"],
    "ENERGY":       ["oil", "crude", "gas", "lng", "opec", "barrel", "energy", "fuel"],
    "HUMANITARIAN": ["displaced", "refugee", "aid agenc", "aid convoy", "famine", "food", "civilians", "humanitarian"],
}
DEFAULT_DOMAIN = "GEOPOLITICAL"

DOMAIN_COLORS = {
    "MARITIME":     ("#dde8f3", "#1f4e79"),
    "AIR":          ("#e3eef7", "#2f5f8a"),
    "MISSILE":      ("#f4dede", "#8a1f1f"),
    "NUCLEAR":      ("#f6ead2", "#8a5a12"),
    "LAND":         ("#e6ecdf", "#3f5a2a"),
    "CYBER":        ("#e9e2f3", "#4b2f79"),
    "SPACE":        ("#e2e6f3", "#2f3a79"),
    "SECURITY":     ("#f3e2ea", "#792f50"),
    "DIPLOMATIC":   ("#eceae4", "#55524a"),
    "ENERGY":       ("#f6efd2", "#7a6312"),
    "HUMANITARIAN": ("#f3e8e2", "#79482f"),
    DEFAULT_DOMAIN: ("#eceae4", "#6b6b68"),
}


def _hits(text: str, keywords: list) -> int:
    return sum(len(re.findall(r"\b" + re.escape(k), text)) for k in keywords)


def classify(cluster: dict) -> str:
    """Highest-scoring operational domain for a thread, or GEOPOLITICAL."""
    titles = " ".join(a.get("title", "") for a in cluster["articles"]).lower()
    bodies = " ".join(a.get("content", "")[:1500] for a in cluster["articles"]).lower()
    scores = {
        domain: 3 * _hits(titles, keywords) + _hits(bodies, keywords)
        for domain, keywords in DOMAINS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else DEFAULT_DOMAIN
