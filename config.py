# config.py
# ─────────────────────────────────────────────────────────
# Central configuration. Every module imports from here —
# never call os.getenv directly outside this file.
#
# In production (FLASK_ENV=production) this module fails
# fast if SECRET_KEY or API_V1_KEY are missing / defaults.
# ─────────────────────────────────────────────────────────

import os
import secrets
import warnings

from dotenv import load_dotenv

load_dotenv()

# ── Environment ────────────────────────────────────────────
# One of: development | testing | production
FLASK_ENV = os.getenv("FLASK_ENV", "development").strip().lower()
IS_PRODUCTION = FLASK_ENV == "production"
IS_TESTING    = FLASK_ENV == "testing" or os.getenv("PYTEST_CURRENT_TEST") is not None

# ── Flask core ─────────────────────────────────────────────
_DEV_SECRET_DEFAULTS = {
    "",
    "qms-genai-dev-key",
    "qms-genai-secret-change-in-production",
    "test-secret",
    "change-me",
}

_configured_secret = (os.getenv("SECRET_KEY") or "").strip()

if IS_PRODUCTION:
    if _configured_secret in _DEV_SECRET_DEFAULTS:
        raise RuntimeError(
            "SECRET_KEY is missing or set to a known dev default. "
            "Set a strong SECRET_KEY (>=32 random chars) before starting the app in production."
        )
    if len(_configured_secret) < 32:
        raise RuntimeError(
            "SECRET_KEY must be at least 32 characters in production."
        )
    SECRET_KEY = _configured_secret
else:
    if _configured_secret and _configured_secret not in _DEV_SECRET_DEFAULTS:
        SECRET_KEY = _configured_secret
    else:
        # Generate a per-process ephemeral key so dev sessions never share a secret.
        SECRET_KEY = _configured_secret or secrets.token_urlsafe(48)
        if _configured_secret in _DEV_SECRET_DEFAULTS and _configured_secret:
            warnings.warn(
                "SECRET_KEY is set to a known dev default. Generating an ephemeral "
                "SECRET_KEY for this process. Rotate it before deploying.",
                stacklevel=2,
            )

PORT = int(os.getenv("PORT", "5000"))

# ── Cookie / session hardening ─────────────────────────────
SESSION_COOKIE_SECURE   = os.getenv("SESSION_COOKIE_SECURE", "true" if IS_PRODUCTION else "false").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
PERMANENT_SESSION_LIFETIME_SECONDS = int(os.getenv("SESSION_LIFETIME_SECONDS", "3600"))

# ── CSRF ───────────────────────────────────────────────────
CSRF_ENABLED = os.getenv("CSRF_ENABLED", "true").lower() == "true" and not IS_TESTING
CSRF_TIME_LIMIT_SECONDS = int(os.getenv("CSRF_TIME_LIMIT_SECONDS", "3600"))

# ── Rate limiting ──────────────────────────────────────────
RATE_LIMIT_ENABLED  = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true" and not IS_TESTING
RATE_LIMIT_STORAGE  = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
RATE_LIMIT_DEFAULT  = os.getenv("RATE_LIMIT_DEFAULT",  "200 per minute")
RATE_LIMIT_LOGIN    = os.getenv("RATE_LIMIT_LOGIN",    "5 per minute; 20 per hour")
RATE_LIMIT_API_V1   = os.getenv("RATE_LIMIT_API_V1",   "60 per minute")
RATE_LIMIT_AGENTS   = os.getenv("RATE_LIMIT_AGENTS",   "10 per minute; 60 per hour")

# ── Login lockout ──────────────────────────────────────────
LOGIN_LOCKOUT_ATTEMPTS = int(os.getenv("LOGIN_LOCKOUT_ATTEMPTS", "5"))
LOGIN_LOCKOUT_WINDOW_SECONDS  = int(os.getenv("LOGIN_LOCKOUT_WINDOW_SECONDS",  "300"))
LOGIN_LOCKOUT_COOLDOWN_SECONDS= int(os.getenv("LOGIN_LOCKOUT_COOLDOWN_SECONDS","900"))

# ── Password policy ────────────────────────────────────────
# Weaker in dev so admin/admin still works for testing.
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12" if IS_PRODUCTION else "4"))
PASSWORD_REQUIRE_COMPLEXITY = os.getenv(
    "PASSWORD_REQUIRE_COMPLEXITY", "true" if IS_PRODUCTION else "false"
).lower() == "true"

# ── Seed credentials gating ────────────────────────────────
# By default seed accounts (admin/admin, quality/admin, shashi/admin) load in every non-prod env.
# In production they load only if SEED_BUILTIN_USERS=true is explicitly set.
SEED_BUILTIN_USERS = os.getenv(
    "SEED_BUILTIN_USERS", "false" if IS_PRODUCTION else "true"
).lower() == "true"

# ── API v1 auth ────────────────────────────────────────────
API_V1_KEY = os.getenv("API_V1_KEY", "").strip()
API_V1_ALLOW_ANONYMOUS = os.getenv(
    "API_V1_ALLOW_ANONYMOUS", "false" if IS_PRODUCTION else "true"
).lower() == "true"

if IS_PRODUCTION and not API_V1_KEY and not API_V1_ALLOW_ANONYMOUS:
    # Fail-closed: production MUST have API_V1_KEY set.
    raise RuntimeError(
        "API_V1_KEY is required in production. "
        "Set API_V1_KEY, or explicitly set API_V1_ALLOW_ANONYMOUS=true (not recommended)."
    )

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "https://*.salesforce.com,https://*.force.com,http://localhost:5000",
    ).split(",")
    if o.strip()
]

SF_WEBHOOK_SECRET = os.getenv("SF_WEBHOOK_SECRET", "").strip()
if IS_PRODUCTION and not SF_WEBHOOK_SECRET:
    warnings.warn(
        "SF_WEBHOOK_SECRET is not set in production. The Salesforce webhook will reject all traffic.",
        stacklevel=2,
    )

# ── Mock mode ─────────────────────────────────────────────
# True  → uses template-based mock responses (no API key needed)
# False → calls the real AI provider set below
MOCK_MODE  = os.getenv("MOCK_MODE", "true").lower() == "true"

# ── AI Provider config ────────────────────────────────────
# Change these in .env to switch AI provider — no code changes needed.
# Supported: mock | openai | anthropic | azure | gemini | groq | bedrock
AI_PROVIDER = os.getenv("AI_PROVIDER", "mock")
AI_API_KEY  = os.getenv("AI_API_KEY",  "")
AI_MODEL    = os.getenv("AI_MODEL",    "mock-mode")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")   # needed for Azure OpenAI

# ── LLM resilience knobs ───────────────────────────────────
LLM_TIMEOUT_SECONDS   = float(os.getenv("LLM_TIMEOUT_SECONDS",   "60"))
LLM_MAX_RETRIES       = int(os.getenv("LLM_MAX_RETRIES",         "3"))
LLM_CB_THRESHOLD      = int(os.getenv("LLM_CB_THRESHOLD",        "5"))
LLM_CB_COOLDOWN_SECS  = int(os.getenv("LLM_CB_COOLDOWN_SECS",    "30"))

# ── Agent supervisor ──────────────────────────────────────
AGENT_KILL_SWITCH    = os.getenv("AGENT_KILL_SWITCH", "false").lower() == "true"
AGENT_MAX_TURNS      = int(os.getenv("AGENT_MAX_TURNS", "12"))
AGENT_MAX_RETRIES    = int(os.getenv("AGENT_MAX_RETRIES", "2"))
AGENT_DEADLETTER_MAX = int(os.getenv("AGENT_DEADLETTER_MAX", "100"))

# ── Logging ────────────────────────────────────────────────
LOG_LEVEL  = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if IS_PRODUCTION else "text").lower()
