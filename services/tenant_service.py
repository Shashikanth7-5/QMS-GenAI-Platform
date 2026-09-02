"""Multi-tenant API-key + webhook secret management.

Tenants are stored in ``qms_api_tenants``. API keys are never persisted
in cleartext — we store the HMAC-SHA256 digest of ``sha256(tenant_id + key)``
so a leaked DB dump cannot be replayed against the API.

Boot-time single-tenant compatibility: if no tenants exist but the legacy
``API_V1_KEY`` env is set, we accept it as a fallback for tenant_id="_legacy"
so existing integrations keep working during migration.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from services.logging_config import get_logger

log = get_logger(__name__)


def _digest(tenant_id: str, api_key: str) -> str:
    """Constant-time HMAC digest — tenant_id serves as the salt."""
    mac = hmac.new(tenant_id.encode(), api_key.encode(), hashlib.sha256)
    return mac.hexdigest()


def _session():
    from database import SessionLocal
    return SessionLocal()


def generate_api_key() -> str:
    """32-byte URL-safe token. Store the digest, hand the raw key to the caller once."""
    return secrets.token_urlsafe(32)


def create_tenant(
    tenant_id: str,
    *,
    display_name: str = "",
    origin_allowlist: Optional[list[str]] = None,
    webhook_secret: Optional[str] = None,
    rate_limit: str = "120 per minute; 2000 per hour",
    api_key_override: Optional[str] = None,
) -> tuple[dict, str]:
    """
    Provision a new tenant. Returns (tenant_dict, raw_api_key).
    The raw key is displayed ONCE — caller must hand it to the tenant.

    ``api_key_override`` lets the caller supply a pre-decided key
    (e.g. from an env var during pilot bootstrap) instead of generating
    a new one. Only the digest is stored either way.
    """
    from models import ApiTenant
    raw_key = api_key_override or generate_api_key()
    with _session() as session:
        existing = session.query(ApiTenant).filter(ApiTenant.tenant_id == tenant_id).first()
        if existing:
            raise ValueError(f"tenant '{tenant_id}' already exists")
        row = ApiTenant(
            tenant_id=tenant_id,
            display_name=display_name or tenant_id,
            api_key_hash=_digest(tenant_id, raw_key),
            webhook_secret=webhook_secret or "",
            origin_allowlist=origin_allowlist or [],
            rate_limit=rate_limit,
            status="active",
        )
        session.add(row)
        session.commit()
        return row.to_dict(), raw_key


def get_tenant(tenant_id: str) -> Optional[dict]:
    """Return the tenant dict without needing the API key. Used by bootstrap
    scripts + admin UI. Never call from a request handler — use
    resolve_tenant(tenant_id, api_key) so the key is verified."""
    from models import ApiTenant
    try:
        with _session() as session:
            row = session.query(ApiTenant).filter(ApiTenant.tenant_id == tenant_id).first()
            return row.to_dict() if row else None
    except Exception:
        log.warning("tenant.get_failed", exc_info=True, extra={"tenant_id": tenant_id})
        return None


def resolve_tenant(tenant_id: str, api_key: str) -> Optional[dict]:
    """
    Return the tenant row iff (tenant_id, api_key) is valid + active.
    Falls back to the legacy single-tenant API_V1_KEY only when no
    qms_api_tenants rows exist at all (bootstrap safety).
    """
    if not tenant_id or not api_key:
        return None
    try:
        from models import ApiTenant
        with _session() as session:
            row = session.query(ApiTenant).filter(
                ApiTenant.tenant_id == tenant_id,
                ApiTenant.status == "active",
            ).first()
            if row is None:
                # Legacy fallback: only when the tenants table is empty.
                total = session.query(ApiTenant).count()
                if total == 0:
                    legacy = (os.getenv("API_V1_KEY") or "").strip()
                    if legacy and hmac.compare_digest(api_key, legacy) and tenant_id in ("_legacy", "default"):
                        return {"tenantId": tenant_id, "displayName": "legacy",
                                "status": "active", "rateLimit": "60 per minute",
                                "originAllowlist": [], "webhookSecret": legacy}
                return None
            if not hmac.compare_digest(row.api_key_hash, _digest(tenant_id, api_key)):
                return None
            row.last_used_at = datetime.utcnow()
            session.commit()
            data = row.to_dict()
            # Expose the webhook secret only to code inside the request scope.
            data["webhookSecret"] = row.webhook_secret or ""
            return data
    except Exception:
        log.warning("tenant.resolve_failed", exc_info=True, extra={"tenant_id": tenant_id})
        return None


def revoke_tenant(tenant_id: str) -> bool:
    from models import ApiTenant
    try:
        with _session() as session:
            row = session.query(ApiTenant).filter(ApiTenant.tenant_id == tenant_id).first()
            if not row:
                return False
            row.status = "revoked"
            row.revoked_at = datetime.utcnow()
            session.commit()
            return True
    except Exception:
        log.warning("tenant.revoke_failed", exc_info=True)
        return False


def list_tenants() -> list[dict]:
    from models import ApiTenant
    try:
        with _session() as session:
            rows = session.query(ApiTenant).order_by(ApiTenant.created_at.desc()).all()
            return [r.to_dict() for r in rows]
    except Exception:
        return []


# ────────────────────────────────────────────────────────────
# Idempotency + webhook replay protection
# ────────────────────────────────────────────────────────────

def check_and_record_idempotency(
    *,
    tenant_id: str,
    key: str,
    method: str,
    path: str,
    request_body: bytes,
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Returns (cached_response, conflict). Semantics:
        - No prior row       → (None, None)  -> caller proceeds and stores response.
        - Same key + same request body → (cached_response, None)  -> caller returns cached.
        - Same key + different body    → (None, {"error": "..."})  -> caller returns 409.
    """
    from models import IdempotencyKey
    body_hash = hashlib.sha256(request_body or b"").hexdigest()
    try:
        with _session() as session:
            row = session.query(IdempotencyKey).filter(
                IdempotencyKey.tenant_id == tenant_id,
                IdempotencyKey.key == key,
            ).first()
            if row is None:
                return None, None
            if row.request_hash != body_hash:
                return None, {
                    "error": "Idempotency-Key was reused with a different request body.",
                    "code": "idempotency_conflict",
                }
            return {"status_code": row.status_code, "response_json": row.response_json or {}}, None
    except Exception:
        log.warning("idempotency.check_failed", exc_info=True)
        return None, None


def store_idempotent_response(
    *,
    tenant_id: str,
    key: str,
    method: str,
    path: str,
    request_body: bytes,
    status_code: int,
    response_json: dict,
) -> None:
    from models import IdempotencyKey
    try:
        with _session() as session:
            row = IdempotencyKey(
                tenant_id=tenant_id,
                key=key,
                method=method,
                path=path,
                request_hash=hashlib.sha256(request_body or b"").hexdigest(),
                status_code=status_code,
                response_json=response_json or {},
            )
            session.add(row)
            session.commit()
    except Exception:
        log.warning("idempotency.store_failed", exc_info=True)


def record_webhook_nonce(*, tenant_id: str, nonce: str) -> bool:
    """
    Insert (tenant_id, nonce). Returns True if it was new (safe to accept),
    False if already seen within the retention window (replay attack).
    """
    from models import WebhookNonce
    try:
        with _session() as session:
            row = WebhookNonce(tenant_id=tenant_id, nonce=nonce)
            session.add(row)
            session.commit()
            return True
    except Exception:
        # IntegrityError from the unique index = replay.
        return False


def prune_old_nonces(*, max_age_minutes: int = 30) -> int:
    from models import WebhookNonce
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        with _session() as session:
            deleted = session.query(WebhookNonce).filter(WebhookNonce.seen_at < cutoff).delete()
            session.commit()
            return int(deleted or 0)
    except Exception:
        return 0
