"""
Ranks today's clusters and tags each with a trend, by comparing against
the last few days of cluster snapshots (fde/store.py).

Trend logic (deliberately simple for v1):
  - No matching cluster in the last 3 days  -> DEVELOPING (a new thread)
  - Matching cluster, today's count is higher -> ESCALATING
  - Matching cluster, today's count is flat/lower -> STEADY

"Matching" = at least 30% entity overlap (Jaccard) with a past snapshot.
"""

import logging

from fde.store import get_recent_snapshots, save_cluster_snapshot

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 0.3


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_clusters(clusters: list) -> list:
    """
    Annotate each cluster with 'trend', 'article_count', 'source_count',
    sort by (source_count, article_count) descending, and persist today's
    snapshot of every cluster for tomorrow's comparison.

    Returns the same list of cluster dicts, scored and sorted.
    """
    past_snapshots = get_recent_snapshots(days=3)

    for cluster in clusters:
        articles = cluster["articles"]
        cluster["article_count"] = len(articles)
        cluster["source_count"] = len({a["source"] for a in articles})

        best_match = None
        best_overlap = 0.0
        for snap in past_snapshots:
            overlap = _jaccard(cluster["entities"], snap["entities"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = snap

        if best_match is None or best_overlap < _MATCH_THRESHOLD:
            cluster["trend"] = "DEVELOPING"
        elif cluster["article_count"] > best_match["article_count"]:
            cluster["trend"] = "ESCALATING"
        else:
            cluster["trend"] = "STEADY"

    clusters.sort(key=lambda c: (c["source_count"], c["article_count"]), reverse=True)

    for cluster in clusters:
        save_cluster_snapshot(cluster["entities"], cluster["article_count"], cluster["source_count"])

    logger.info("Scorer: ranked %d clusters", len(clusters))
    return clusters
