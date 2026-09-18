"""
Dual-model sentiment analysis for news articles.

Models used:
  - cardiffnlp/twitter-roberta-base-sentiment-latest  (general news)
  - ProsusAI/finbert                                   (finance news)

Both models are loaded lazily on first use. Their softmax probabilities are
averaged (ensemble) to produce a single label: positive / negative / neutral.

ScanX articles with existing sentiment are skipped.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Limit PyTorch internal threads BEFORE torch is imported anywhere.
# This prevents OpenMP from spawning threads that conflict with Flask's
# threading model, which causes segmentation faults.
try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except Exception:
    pass

GENERAL_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
FINANCE_MODEL = "ProsusAI/finbert"

LABELS = ("positive", "negative", "neutral")

SKIP_SOURCES = {"ScanX"}


def _normalize_label(label: str) -> str:
    """Map any model label variant → positive / negative / neutral."""
    label = label.lower()
    if "pos" in label or label == "label_2":
        return "positive"
    if "neg" in label or label == "label_0":
        return "negative"
    return "neutral"


class SentimentAnalyzer:
    """
    Lazy-loading, thread-safe dual-model sentiment analyzer.

    Both models are downloaded from HuggingFace on first use (~500 MB total).
    Subsequent runs use the local cache.
    """

    def __init__(self):
        self._general = None
        self._finance = None
        self._lock = threading.Lock()

    def _load(self):
        """Load both pipelines. Called inside self._lock so it only runs once."""
        from transformers import pipeline  # noqa: PLC0415

        if self._general is None:
            logger.info("Loading general sentiment model: %s", GENERAL_MODEL)
            self._general = pipeline(
                "sentiment-analysis",
                model=GENERAL_MODEL,
                top_k=None,
                truncation=True,
                max_length=512,
            )

        if self._finance is None:
            try:
                logger.info("Loading finance sentiment model: %s", FINANCE_MODEL)
                self._finance = pipeline(
                    "sentiment-analysis",
                    model=FINANCE_MODEL,
                    top_k=None,
                    truncation=True,
                    max_length=512,
                )
            except Exception as e:
                logger.warning("Finance model unavailable (%s), using general model only", e)
                self._finance = False  # sentinel: don't retry

    def analyze(self, text: str) -> str:
        """
        Analyze text and return 'positive', 'negative', or 'neutral'.

        Runs both models and ensembles probabilities. Falls back to general
        model only if the finance model failed to load.
        """
        if not text or not text.strip():
            return "neutral"

        # Truncate early to avoid tokenizer overflow warnings
        text = text[:1024]

        with self._lock:
            self._load()

            gen_results = self._general(text)[0]

            if self._finance:
                fin_results = self._finance(text)[0]
            else:
                fin_results = None

        def to_probs(results):
            return {_normalize_label(r["label"]): r["score"] for r in results}

        gen = to_probs(gen_results)

        if fin_results:
            fin = to_probs(fin_results)
            # Ensemble: simple average of both model's probabilities
            combined = {
                lbl: (gen.get(lbl, 0.0) + fin.get(lbl, 0.0)) / 2.0
                for lbl in LABELS
            }
        else:
            combined = gen

        return max(combined, key=combined.get)

    def analyze_batch(self, texts: list) -> list:
        """
        Analyze a list of texts in one batched forward pass per model.
        Returns a list of labels in the same order. Much faster than one-by-one.
        """
        if not texts:
            return []

        import torch  # noqa: PLC0415

        texts = [t[:512] if t else "" for t in texts]

        with self._lock:
            self._load()
            with torch.no_grad():
                # batch_size=8 is safe on CPU — avoids memory spikes
                gen_batch = self._general(texts, batch_size=8, truncation=True)
                fin_batch = (
                    self._finance(texts, batch_size=8, truncation=True)
                    if self._finance else None
                )

        def to_probs(results):
            return {_normalize_label(r["label"]): r["score"] for r in results}

        labels = []
        for i, gen_results in enumerate(gen_batch):
            gen = to_probs(gen_results)
            if fin_batch:
                fin = to_probs(fin_batch[i])
                combined = {lbl: (gen.get(lbl, 0.0) + fin.get(lbl, 0.0)) / 2.0 for lbl in LABELS}
            else:
                combined = gen
            labels.append(max(combined, key=combined.get))

        return labels


# Module-level singleton — shared across all threads
_analyzer: SentimentAnalyzer | None = None


def get_analyzer() -> SentimentAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer


def sentiment_worker(interval: int = 30) -> None:
    """
    Background daemon thread.

    Polls for articles with empty sentiment, runs them through both models
    in a single batched forward pass, then writes results back to the DB.
    interval: seconds to sleep between batches (default 30 s).
    """
    from storage import db  # noqa: PLC0415

    analyzer = get_analyzer()
    logger.info("🧠 Sentiment worker started (interval: %ds)", interval)

    while True:
        try:
            articles = db.get_unanalyzed(limit=32)
            if articles:
                texts = [
                    f"{a['title']} {a.get('content', '')}".strip()
                    for a in articles
                ]
                logger.info("🧠 Sentiment: batch-analysing %d articles", len(articles))
                try:
                    labels = analyzer.analyze_batch(texts)
                    for art, label in zip(articles, labels):
                        db.update_sentiment(art["id"], label)
                    logger.info("🧠 Sentiment: done — %d labelled", len(labels))
                except Exception as exc:
                    logger.error("Sentiment batch failed: %s", exc)
        except Exception as exc:
            logger.error("Sentiment worker error: %s", exc)

        time.sleep(interval)
