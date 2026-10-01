"""
Groups articles into story threads and merges each thread's extracted
relationships into a connection graph — the "who did what to whom"
behind the story, not just which entities co-occur.

extractor.py does one LLM call per article to name its entities and
relationships. This module does the deterministic half: deciding which
articles are about the same story.

Clustering notes (both of these matter — a naive version gets this badly
wrong):

  * Articles are matched against a cluster's CORE (what its members
    actually have in common), not pairwise. Pairwise matching plus
    union-find chains A-B, B-C, C-D into one component even when A and D
    share nothing, which collapses a whole day's news into one blob.

  * Which entities count as signal is decided per run from document
    frequency, not a fixed stoplist. "Iran" and "US" are always noise
    here by definition of the topic, but on any given day something else
    ("Strait of Hormuz" during a Hormuz crisis) can be just as ubiquitous
    and just as useless for telling threads apart.
"""

import logging
import math
import re
from collections import Counter

from fde.extractor import extract

logger = logging.getLogger(__name__)

# Always noise in a US-Iran briefing — every article has them by definition.
_ALWAYS_GENERIC = {
    "iran", "iranian", "irani", "us", "u.s.", "u.s", "usa", "united states",
    "united states of america", "america", "american", "washington", "tehran",
}

# An entity in more than this share of the day's articles carries no
# discriminating signal. Only applied once there are enough articles for
# the ratio to mean anything.
_GENERIC_DF_RATIO = 0.25
_MIN_ARTICLES_FOR_DF = 8

# A single shared entity can link two articles only if it's a participant
# in both stories and isn't one of the day's common names.
_SINGLE_LINK_MAX_DF_RATIO = 0.15

# Otherwise, two articles need this many shared entities to be one thread.
_MIN_SHARED = 2


def _normalize_entity(value: str) -> str:
    """Lowercase and flatten punctuation so name variants match each other
    ('Lee Jae-myung' and 'Lee Jae Myung' are the same person, and otherwise
    two articles about him look like they share nothing)."""
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _normalized_entities(entities: dict) -> set:
    """Flatten people/orgs/locations/weapon_systems into one lowercase set."""
    flat = set()
    for key in ("people", "orgs", "locations", "weapon_systems"):
        for value in entities.get(key, []) or []:
            if value and isinstance(value, str):
                cleaned = _normalize_entity(value)
                if cleaned:
                    flat.add(cleaned)
    return flat


def _central_entities(entities: dict) -> set:
    """Entities that actually take part in the story — the subjects and
    objects of its extracted relationships. An entity mentioned only in
    passing ("France" in a list of countries) is not evidence that two
    articles are about the same event, however rare it is overall."""
    central = set()
    for r in entities.get("relationships", []) or []:
        for key in ("subject", "object"):
            value = _normalize_entity(r.get(key) or "")
            if value:
                central.add(value)
    return central


def _document_frequency(entity_sets: list) -> Counter:
    df = Counter()
    for entities in entity_sets:
        df.update(entities)
    return df


def _signal_entities(flat: set, df: Counter, total: int) -> set:
    """The subset of an article's entities specific enough to match on."""
    signal = set()
    for entity in flat:
        if entity in _ALWAYS_GENERIC:
            continue
        if total >= _MIN_ARTICLES_FOR_DF and df[entity] / total > _GENERIC_DF_RATIO:
            continue
        signal.add(entity)
    return signal


# Wire services run the same story under slightly different headlines, and
# they often come out of extraction with slightly different entities, so
# they land in separate threads. Comparing headline wording catches those.
_TITLE_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "as", "is", "are", "was", "were", "be", "been",
    "will", "would", "says", "say", "said", "after", "over", "amid", "its",
    "his", "her", "their", "that", "this", "it", "not", "no", "new", "more",
    "out", "up", "into", "about", "who", "what", "how", "why", "than", "then",
    "may", "might", "can", "could", "have", "has", "had", "does", "did",
}

# Headlines refer to the same bodies different ways ("United Nations" vs
# "UN"), which otherwise reads as two unrelated stories.
_TITLE_SYNONYMS = {
    ("united", "nations"): "un",
    ("united", "states"): "us",
    ("islamic", "revolutionary", "guard", "corps"): "irgc",
    ("central", "command"): "centcom",
}

_TITLE_DUPLICATE_THRESHOLD = 0.40
_MEMBER_DUPLICATE_THRESHOLD = 0.60
_SHORT_TOKEN_KEEP = {"un", "us", "uk", "eu", "oil", "gas", "war", "jet", "f35"}


def _title_tokens(title: str) -> set:
    words = re.findall(r"[a-z0-9]+", (title or "").lower())

    for phrase, replacement in _TITLE_SYNONYMS.items():
        length = len(phrase)
        i = 0
        while i <= len(words) - length:
            if tuple(words[i:i + length]) == phrase:
                words[i:i + length] = [replacement]
            i += 1

    return {
        w for w in words
        if w not in _TITLE_STOPWORDS and (len(w) > 2 or w in _SHORT_TOKEN_KEEP)
    }


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Titles that say nothing on their own — fine as a source, useless as the
# headline of a briefing section ("Iran Update, September 17, 2026").
# Matches "Iran Update, ...", "Morning update", "Live blog: ...", etc.
_GENERIC_TITLE_RE = re.compile(r"^\s*(\w+\s+)?(updates?|live blog|liveblog)\b", re.I)


def _is_generic_title(title: str) -> bool:
    return bool(_GENERIC_TITLE_RE.match(title or ""))


def _order_articles(articles: list, signal_sets: list = None) -> list:
    """Lead with the article that best represents the thread: a real
    headline first, then the one sharing the most entities with its
    thread-mates, then the longest. Content length alone picks articles
    whose headline has nothing to do with what the section ends up saying."""
    def representativeness(item):
        if not signal_sets:
            return 0
        index, _ = item
        others = set()
        for other_index, entities in enumerate(signal_sets):
            if other_index != index:
                others |= entities
        return len(signal_sets[index] & others)

    def relationship_count(article):
        return len((article.get("_entities") or {}).get("relationships") or [])

    indexed = list(enumerate(articles))
    indexed.sort(
        key=lambda item: (
            not _is_generic_title(item[1].get("title", "")),
            representativeness(item),
            # Overlap is symmetric, so it can't separate a pair — prefer the
            # article with more of an actual story in it.
            relationship_count(item[1]),
            len(item[1].get("content", "")),
        ),
        reverse=True,
    )
    return [article for _, article in indexed]


def _is_same_story(a: dict, b: dict) -> bool:
    """Lead headlines that are near-duplicates, or any pair of member
    headlines that are almost identical — a wire story republished by
    another outlet can sit in a thread led by a different headline."""
    if _jaccard(_title_tokens(a["articles"][0]["title"]),
                _title_tokens(b["articles"][0]["title"])) >= _TITLE_DUPLICATE_THRESHOLD:
        return True
    tokens_b = [_title_tokens(x["title"]) for x in b["articles"]]
    return any(
        _jaccard(_title_tokens(x["title"]), t) >= _MEMBER_DUPLICATE_THRESHOLD
        for x in a["articles"] for t in tokens_b
    )


def _merge_near_duplicate_threads(clusters: list) -> list:
    """Fold together threads that carry the same story under different wording."""
    merged_any = True
    while merged_any:
        merged_any = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if not _is_same_story(clusters[i], clusters[j]):
                    continue
                target, source = clusters[i], clusters.pop(j)
                target["articles"] = _order_articles(target["articles"] + source["articles"])
                target["entities"] |= source["entities"]
                seen = {
                    (r["subject"].lower(), r["relation"].lower(), r["object"].lower())
                    for r in target["relationships"]
                }
                for r in source["relationships"]:
                    key = (r["subject"].lower(), r["relation"].lower(), r["object"].lower())
                    if key not in seen:
                        seen.add(key)
                        target["relationships"].append(r)
                merged_any = True
                break
            if merged_any:
                break
    return clusters


def _merge_relationships(entities_list: list) -> list:
    """Dedupe {subject, relation, object} triples across a cluster's articles."""
    seen = set()
    merged = []
    for entities in entities_list:
        for r in entities.get("relationships", []) or []:
            key = (r["subject"].strip().lower(), r["relation"].strip().lower(), r["object"].strip().lower())
            if key not in seen:
                seen.add(key)
                merged.append(r)
    return merged


class _Thread:
    """One story thread under construction."""

    def __init__(self, index: int, signal: set, central: set):
        self.indices = [index]
        self.signal_sets = [signal]
        self.central = set(central)
        self.core = set(signal)

    def add(self, index: int, signal: set, central: set):
        self.indices.append(index)
        self.signal_sets.append(signal)
        self.central |= central
        self._recompute_core()

    def _recompute_core(self):
        """Entities shared by at least half the members (minimum two), so the
        core tightens toward what the thread is genuinely about as it grows."""
        counts = Counter()
        for signal in self.signal_sets:
            counts.update(signal)
        needed = max(2, math.ceil(len(self.signal_sets) / 2))
        self.core = {entity for entity, count in counts.items() if count >= needed}

    def score(self, signal: set, central: set, df: Counter, total: int):
        """How well an article matches this thread — rarer shared entities
        count for more. Returns 0.0 when it isn't a match at all.

        A single shared entity only links two articles when it's rare AND
        a participant in both stories; otherwise one incidental mention in
        common (a country named in passing) welds unrelated threads together."""
        shared = signal & self.core
        if not shared:
            return 0.0

        if len(shared) < _MIN_SHARED:
            entity = next(iter(shared))
            corroborated = (
                entity in central
                and entity in self.central
                and df[entity] / total <= _SINGLE_LINK_MAX_DF_RATIO
            )
            if not corroborated:
                return 0.0

        return sum(1.0 / df[e] for e in shared)


def build_clusters(articles: list) -> list:
    """
    Run entity + relationship extraction on each article, then group the
    articles into story threads.

    Returns a list of dicts:
      {"articles": [...], "entities": set(...), "relationships": [...]}
    """
    if not articles:
        return []

    extracted = []
    entity_sets = []
    central_sets = []
    for article in articles:
        entities = extract(article)
        extracted.append(entities)
        entity_sets.append(_normalized_entities(entities))
        central_sets.append(_central_entities(entities))
        article["_entities"] = entities

    total = len(articles)
    df = _document_frequency(entity_sets)
    signal_sets = [_signal_entities(flat, df, total) for flat in entity_sets]

    # Seed threads with the richest articles first so cores form around
    # well-described stories rather than sparse stubs.
    order = sorted(range(total), key=lambda i: len(signal_sets[i]), reverse=True)

    threads: list = []
    for i in order:
        signal = signal_sets[i]
        central = central_sets[i]
        best_thread, best_score = None, 0.0
        if signal:
            for thread in threads:
                score = thread.score(signal, central, df, total)
                if score > best_score:
                    best_thread, best_score = thread, score

        if best_thread is not None:
            best_thread.add(i, signal, central)
        else:
            threads.append(_Thread(i, signal, central))

    clusters = []
    for thread in threads:
        indices = thread.indices
        merged_entities: set = set()
        for i in indices:
            merged_entities |= entity_sets[i]
        clusters.append({
            # Most representative article first — it supplies the headline.
            "articles": _order_articles(
                [articles[i] for i in indices],
                [signal_sets[i] for i in indices],
            ),
            "entities": merged_entities,
            "relationships": _merge_relationships([extracted[i] for i in indices]),
        })

    before = len(clusters)
    clusters = _merge_near_duplicate_threads(clusters)

    sizes = sorted((len(c["articles"]) for c in clusters), reverse=True)
    logger.info(
        "Linker: %d articles -> %d threads (%d folded as near-duplicates; sizes: %s)",
        total, len(clusters), before - len(clusters), sizes[:10],
    )
    return clusters
