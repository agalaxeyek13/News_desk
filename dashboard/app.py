"""
Flask web dashboard for the News Alert System.
Serves a live-updating news feed at http://0.0.0.0:5050
"""

import sys
import os
import re
import logging
import secrets
from functools import wraps

from flask import Flask, render_template, jsonify, request, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.db import get_recent, get_article_count, get_recent_by_source, get_recent_liveblogs, get_recent_scanx, get_recent_et, get_recent_et_by_category, get_et_categories, get_recent_mc

logger = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Secret key: loaded from environment (set in .env). Falls back to a per-process
# random value which is fine since this app doesn't use persistent sessions.
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# Hard limit on incoming request bodies (protects against large-payload attacks).
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64 KB

# ── Rate limiting ──────────────────────────────────────────────────────────────
# Key: client IP. Default bucket applied to every route unless overridden below.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["300 per minute"],
    headers_enabled=True,          # Sends X-RateLimit-* headers to clients
    storage_uri="memory://",
)

# ── Optional Basic Auth ────────────────────────────────────────────────────────
_DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()

def _require_auth(f):
    """Decorator: enforce HTTP Basic Auth if DASHBOARD_PASSWORD is set in .env."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _DASHBOARD_PASSWORD:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or auth.username != "newsdesk" or not secrets.compare_digest(
            auth.password, _DASHBOARD_PASSWORD
        ):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="NewsDesk", charset="UTF-8"'},
            )
        return f(*args, **kwargs)
    return decorated

# ── Valid input values ─────────────────────────────────────────────────────────
_VALID_SOURCES = {"Al Jazeera", "Reuters", "ScanX", "Economic Times", "MoneyControl"}

# ── Security headers ───────────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Stop browsers from MIME-sniffing the content type
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Legacy XSS filter (IE/old Edge)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Don't send full URL as Referer to third parties
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Disable unnecessary browser features
    response.headers["Permissions-Policy"] = (
        "geolocation=(), camera=(), microphone=(), payment=(), usb=()"
    )
    # Content-Security-Policy:
    #   - Scripts/styles from same origin + inline (required by our single-file frontend)
    #   - Fonts from Google Fonts CDN only
    #   - No frames, no plugins, no object embeds
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none';"
    )
    # Don't advertise the server stack
    response.headers.pop("Server", None)
    # API responses must not be cached by proxies or shared caches
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

# ── Error handlers ─────────────────────────────────────────────────────────────
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"error": "Unauthorized"}), 401

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(429)
def rate_limited(e):
    return jsonify({"error": "Too many requests — slow down"}), 429

@app.errorhandler(413)
def payload_too_large(e):
    return jsonify({"error": "Request too large"}), 413

@app.errorhandler(500)
def server_error(e):
    logger.error("Internal server error: %s", e)
    return jsonify({"error": "Internal server error"}), 500

# ── Helpers ────────────────────────────────────────────────────────────────────
def _get_tracked_slug_count():
    try:
        import main as m
        return len(m.tracked_slugs)
    except Exception:
        return 0

def _get_last_scrape_time():
    try:
        import main as m
        if m.last_scrape_time:
            return m.last_scrape_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass
    return None

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
@limiter.limit("60 per minute")
@_require_auth
def index():
    return render_template("index.html")


@app.route("/api/news")
@limiter.limit("60 per minute")
@_require_auth
def api_news():
    source = request.args.get("source", None)
    if source is not None:
        if source not in _VALID_SOURCES:
            return jsonify({"error": "Invalid source parameter"}), 400
        articles = get_recent_by_source(source, 50)
    else:
        articles = get_recent(100)
    return jsonify({"articles": articles, "total": get_article_count()})


@app.route("/api/news/grouped")
@limiter.limit("120 per minute")
@_require_auth
def api_news_grouped():
    aljazeera = get_recent_by_source("Al Jazeera", 50)
    reuters = get_recent_by_source("Reuters", 50)
    scanx = get_recent_scanx(50)
    et = get_recent_et(50)
    mc = get_recent_mc(50)
    return jsonify({
        "aljazeera": aljazeera,
        "reuters": reuters,
        "scanx": scanx,
        "et": et,
        "mc": mc,
        "total": get_article_count(),
    })


@app.route("/api/news/scanx")
@limiter.limit("120 per minute")
@_require_auth
def api_scanx():
    articles = get_recent_scanx(100)
    return jsonify({"articles": articles, "total": len(articles)})


@app.route("/api/news/live")
@limiter.limit("120 per minute")
@_require_auth
def api_live():
    articles = get_recent_liveblogs(100)
    return jsonify({"articles": articles, "total": len(articles)})


@app.route("/api/news/mc")
@limiter.limit("60 per minute")
@_require_auth
def api_mc_news():
    """All MoneyControl articles, newest scraped first, limit 100."""
    articles = get_recent_mc(100)
    return jsonify({"articles": articles, "total": len(articles)})


@app.route("/api/news/et")
@limiter.limit("60 per minute")
@_require_auth
def api_et_news():
    """All ET articles, newest scraped first, limit 100."""
    articles = get_recent_et(100)
    return jsonify({"articles": articles, "total": len(articles)})


@app.route("/api/news/et/<category>")
@limiter.limit("60 per minute")
@_require_auth
def api_et_category(category):
    """ET articles filtered by category slug, limit 50."""
    # Validate: allow only alphanumeric + underscore to prevent injection
    if not re.match(r'^[a-z0-9_]{1,40}$', category):
        return jsonify({"error": "Invalid category"}), 400
    articles = get_recent_et_by_category(category, 50)
    return jsonify({"articles": articles, "total": len(articles)})


@app.route("/api/news/et/categories")
@limiter.limit("60 per minute")
@_require_auth
def api_et_categories():
    """Distinct ET categories with article counts, sorted by count desc."""
    return jsonify(get_et_categories())


@app.route("/api/status")
@limiter.limit("60 per minute")
@_require_auth
def api_status():
    return jsonify({
        "status": "running",
        "total_articles": get_article_count(),
        "tracked_liveblogs": _get_tracked_slug_count(),
        "last_scrape": _get_last_scrape_time(),
    })

