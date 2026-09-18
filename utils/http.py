"""
Retry-capable HTTP helper for all scrapers.
"""
import requests
import time
import logging

logger = logging.getLogger(__name__)


def get_with_retry(url, headers, timeout=20, max_retries=3, backoff=5):
    """
    GET a URL with automatic retries on failure.
    Raises the last exception if all retries are exhausted.
    """
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, max_retries, e, backoff
                )
                time.sleep(backoff)
            else:
                raise
