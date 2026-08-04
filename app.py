"""app.py — AI Quality Management System

Flask app factory. Handles CSRF, rate limiting, session hardening,
structured logging, and DB bootstrap. Extensions used elsewhere in
the codebase (csrf, limiter) are attached to the app via
`app.extensions` for lookup without circular imports.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask import Flask, jsonify, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from services.logging_config import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def _install_extensions(app: Flask) -> None:
    """Attach CSRF and rate limiter based on config; expose via app.extensions."""
    from config import (
        CSRF_ENABLED,
        CSRF_TIME_LIMIT_SECONDS,
        RATE_LIMIT_DEFAULT,
        RATE_LIMIT_ENABLED,
        RATE_LIMIT_STORAGE,
    )

    # Always init CSRFProtect so csrf_token() is available in templates
    # (test / dev disable enforcement via WTF_CSRF_ENABLED=False).
    app.config["WTF_CSRF_ENABLED"] = CSRF_ENABLED
    app.config["WTF_CSRF_TIME_LIMIT"] = CSRF_TIME_LIMIT_SECONDS
    csrf = CSRFProtect()
    csrf.init_app(app)
    app.extensions["qms_csrf"] = csrf

    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=RATE_LIMIT_STORAGE,
        default_limits=[RATE_LIMIT_DEFAULT] if RATE_LIMIT_ENABLED else [],
        enabled=RATE_LIMIT_ENABLED,
        headers_enabled=True,
    )
    limiter.init_app(app)
    app.extensions["qms_limiter"] = limiter


def _apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # Baseline CSP — templates use inline styles today, so unsafe-inline stays for now.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'none'",
    )
    return response


def create_app() -> Flask:
    from auth.users import get_user_by_id
    from config import (
        IS_PRODUCTION,
        PERMANENT_SESSION_LIFETIME_SECONDS,
        SECRET_KEY,
        SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE,
    )

    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.config.update(
        SECRET_KEY=SECRET_KEY,
        SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=SESSION_COOKIE_SAMESITE,
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=PERMANENT_SESSION_LIFETIME_SECONDS),
        SESSION_REFRESH_EACH_REQUEST=True,
        PREFERRED_URL_SCHEME="https" if IS_PRODUCTION else "http",
        JSON_SORT_KEYS=False,
    )

    _install_extensions(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.page_login"
    login_manager.login_message = "Please log in to access AI Quality Management System."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)

    from routes.agents import agents_bp
    from routes.analytics import analytics_bp
    from routes.api_v1 import api_v1_bp
    from routes.auth import auth_bp
    from routes.capa import capa_bp
    from routes.dashboard import dashboard_bp
    from routes.decision import decision_bp
    from routes.rag import rag_bp
    from routes.rca import rca_bp
    from routes.search import search_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(capa_bp)
    app.register_blueprint(rca_bp)
    app.register_blueprint(decision_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(api_v1_bp)

    # CSRF is only meaningful for cookie-authenticated form/JSON routes.
    # API v1 uses X-API-Key (bearer-style), so it's CSRF-exempt.
    csrf = app.extensions.get("qms_csrf")
    if csrf is not None:
        csrf.exempt(api_v1_bp)

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Route not found", "status": 404}), 404

    @app.errorhandler(429)
    def rate_limited(_e):
        return jsonify({"error": "Too many requests", "status": 429}), 429

    @app.errorhandler(500)
    def server_error(exc):
        log.exception("unhandled.exception", extra={"path": request.path if request else ""})
        return jsonify({"error": "Internal server error", "status": 500}), 500

    @app.template_filter("avatarcolor")
    def avatarcolor(n):
        colors = ["#4f7df3", "#2dd98f", "#f5a623", "#a78bfa", "#f472b6", "#38bdf8"]
        return colors[int(n) % len(colors)]

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"}), 200

    @app.get("/readyz")
    def readyz():
        from database import check_db_connection

        db_ok = check_db_connection()
        payload = {"status": "ok" if db_ok else "degraded", "db": db_ok}
        return jsonify(payload), 200 if db_ok else 503

    app.after_request(_apply_security_headers)
    return app


def _bootstrap_database() -> None:
    """Best-effort DB init. Skipped during pytest so tests control their own fixture."""
    from config import IS_TESTING

    if IS_TESTING:
        return
    try:
        from database import init_db

        init_db()
    except Exception:
        log.exception("database.init.failed")


_bootstrap_database()

app = create_app()


if __name__ == "__main__":
    from config import IS_PRODUCTION, PORT, SEED_BUILTIN_USERS

    banner_creds = "admin / admin  |  quality / admin" if SEED_BUILTIN_USERS else "seed creds disabled (SEED_BUILTIN_USERS=false)"
    log.info(
        "app.startup",
        extra={"port": PORT, "prod": IS_PRODUCTION, "creds": banner_creds},
    )
    debug_flag = os.getenv("FLASK_DEBUG") == "true" and not IS_PRODUCTION
    app.run(host="127.0.0.1", port=PORT, debug=debug_flag)
