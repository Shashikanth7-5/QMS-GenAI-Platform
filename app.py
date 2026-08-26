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
try:
    from flask_wtf.csrf import CSRFProtect
except ModuleNotFoundError:
    CSRFProtect = None

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ModuleNotFoundError:
    Limiter = None

    def get_remote_address():
        return request.remote_addr or "127.0.0.1"

from services.logging_config import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def _install_extensions(app: Flask) -> None:
    """Attach CSRF and rate limiter based on config; expose via app.extensions."""
    from config import (
        CSRF_ENABLED,
        CSRF_TIME_LIMIT_SECONDS,
        IS_PRODUCTION,
        RATE_LIMIT_DEFAULT,
        RATE_LIMIT_ENABLED,
        RATE_LIMIT_STORAGE,
    )

    app.config["WTF_CSRF_ENABLED"] = CSRF_ENABLED
    app.config["WTF_CSRF_TIME_LIMIT"] = CSRF_TIME_LIMIT_SECONDS
    if CSRFProtect is not None:
        # Always init CSRFProtect so csrf_token() is available in templates
        # (test / dev disable enforcement via WTF_CSRF_ENABLED=False).
        csrf = CSRFProtect()
        csrf.init_app(app)
        app.extensions["qms_csrf"] = csrf
    else:
        if IS_PRODUCTION:
            raise RuntimeError("flask-wtf is required in production. Install requirements.txt cleanly.")
        log.warning("dependency.missing", extra={"package": "flask-wtf", "fallback": "csrf_disabled"})

        class _NoopCSRF:
            def exempt(self, *_args, **_kwargs):
                return None

        @app.context_processor
        def _csrf_token_fallback():
            return {"csrf_token": lambda: ""}

        app.extensions["qms_csrf"] = _NoopCSRF()

    if Limiter is not None:
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=RATE_LIMIT_STORAGE,
            default_limits=[RATE_LIMIT_DEFAULT] if RATE_LIMIT_ENABLED else [],
            enabled=RATE_LIMIT_ENABLED,
            headers_enabled=True,
        )
        limiter.init_app(app)
        app.extensions["qms_limiter"] = limiter
    else:
        if IS_PRODUCTION:
            raise RuntimeError("flask-limiter is required in production. Install requirements.txt cleanly.")
        log.warning("dependency.missing", extra={"package": "flask-limiter", "fallback": "rate_limit_disabled"})
        app.extensions["qms_limiter"] = None


def _apply_security_headers(response):
    from config import IS_PRODUCTION
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), payment=(), usb=(), interest-cohort=()",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if IS_PRODUCTION:
        # 6-month HSTS with subdomains and preload readiness.
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=15552000; includeSubDomains",
        )
    # Baseline CSP. 'unsafe-inline' remains until inline scripts/styles are
    # nonce-refactored (Version@2). Chart.js and Google Fonts are allowed.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'",
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
        import socket
        from database import check_db_connection
        from services.storage import storage_status
        from services.celery_app import EAGER

        db_ok = check_db_connection()
        smtp_host = os.getenv("SMTP_HOST", "").strip()
        smtp_ok = bool(smtp_host)
        if smtp_host:
            try:
                with socket.create_connection((smtp_host, int(os.getenv("SMTP_PORT", "25"))), timeout=3):
                    smtp_ok = True
            except OSError:
                smtp_ok = False
        storage = storage_status()
        hardening = {
            "csrf": CSRFProtect is not None,
            "rateLimiter": Limiter is not None,
        }
        payload = {
            "status": "ok" if db_ok and storage.get("writable") else "degraded",
            "db": db_ok,
            "celery": {"eager": EAGER, "brokerConfigured": bool(os.getenv("CELERY_BROKER_URL", "").strip())},
            "smtp": {"configured": bool(smtp_host), "reachable": smtp_ok},
            "storage": storage,
            "hardening": hardening,
        }
        return jsonify(payload), 200 if db_ok and storage.get("writable") else 503

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
