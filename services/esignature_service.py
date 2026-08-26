"""21 CFR Part 11 electronic-signature persistence + verification.

Signatures live in ``qms_esignatures`` (see models.ESignature) and are
chained via SHA-256 across the entire signing history so a regulator can
prove tamper evidence with a single query.

Two entry points:

    record_signature(...)  -> dict   # persist + return the signed row
    verify_chain(limit)    -> dict   # walk the chain and detect breaks

Callers that need to know the signature is valid *before* mutating the
entity (routes/capa.py already does password re-auth in the request
handler) should call ``record_signature`` inside the same transaction
as the entity mutation. This module never touches the entity itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from threading import Lock
from typing import Optional

from services.logging_config import get_logger
from services.security import chain_next

log = get_logger(__name__)

_CHAIN_LOCK = Lock()


REASON_CODES = {
    "capa_approve":       "Approval of CAPA decision",
    "capa_reject":        "Rejection with route-back for correction",
    "capa_close":         "Final closure after effectiveness verification",
    "record_release":     "Release of record for downstream processing",
    "record_reopen":      "Reopening of previously closed record",
    "override":           "Override of automated decision (documented reason required)",
}


@contextmanager
def _session():
    from database import SessionLocal

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def record_signature(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    meaning: str,
    signer_username: str,
    signer_role: str = "",
    signer_full_name: str = "",
    signer_ip: Optional[str] = None,
    signer_user_agent: Optional[str] = None,
    reason_code: Optional[str] = None,
    reason_text: Optional[str] = None,
    content_hash: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """Persist one Part 11 e-signature and return it (with prev/row hash).

    Falls back to a warning log + empty dict if the DB is unreachable —
    the caller (route handler) will already have written its own audit
    trail via services.audit_service.log().
    """
    from models import ESignature

    signed_at = datetime.utcnow()
    entry = {
        "entityType": entity_type,
        "entityId":   entity_id,
        "action":     action,
        "meaning":    meaning,
        "signer":     signer_username,
        "role":       signer_role or "",
        "reasonCode": reason_code or "",
        "reasonText": reason_text or "",
        "contentHash": content_hash or "",
        "tenantId":   tenant_id or "",
        "timestamp":  signed_at.isoformat(),
    }

    try:
        with _CHAIN_LOCK, _session() as session:
            last = (
                session.query(ESignature)
                .order_by(ESignature.id.desc())
                .limit(1)
                .one_or_none()
            )
            prev_hash = (last.row_hash or "") if last else ""
            row_hash = chain_next(prev_hash, entry)
            row = ESignature(
                tenant_id=tenant_id or None,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                meaning=meaning,
                signer_username=signer_username,
                signer_role=signer_role or "",
                signer_full_name=signer_full_name or "",
                signer_ip=signer_ip,
                signer_user_agent=signer_user_agent,
                reason_code=reason_code,
                reason_text=reason_text,
                content_hash=content_hash,
                prev_hash=prev_hash,
                row_hash=row_hash,
                signed_at=signed_at,
            )
            session.add(row)
            session.flush()
            snapshot = row.to_dict()
            return snapshot
    except Exception:
        log.exception("esignature.persist_failed",
                      extra={"entity_type": entity_type, "entity_id": entity_id,
                             "action": action, "signer": signer_username})
        return {}


def signatures_for_entity(entity_type: str, entity_id: str) -> list[dict]:
    """Return every signature bound to (entity_type, entity_id), oldest first."""
    try:
        from models import ESignature

        with _session() as session:
            rows = (
                session.query(ESignature)
                .filter(ESignature.entity_type == entity_type,
                        ESignature.entity_id == entity_id)
                .order_by(ESignature.id.asc())
                .all()
            )
            snapshots = [r.to_dict() for r in rows]
            return snapshots
    except Exception:
        log.exception("esignature.read_failed",
                      extra={"entity_type": entity_type, "entity_id": entity_id})
        return []


def verify_chain(limit: int = 1000) -> dict:
    """Recompute the chain over the newest ``limit`` signatures.

    Returns ``{"ok": bool, "checked": int, "broken_at": Optional[int]}``.
    """
    try:
        from models import ESignature

        with _session() as session:
            rows = (
                session.query(ESignature)
                .order_by(ESignature.id.asc())
                .limit(limit)
                .all()
            )
            # Materialise every attribute before the session closes.
            snapshots = [{
                "id":          r.id,
                "entityType":  r.entity_type,
                "entityId":    r.entity_id,
                "action":      r.action,
                "meaning":     r.meaning,
                "signer":      r.signer_username,
                "role":        r.signer_role or "",
                "reasonCode":  r.reason_code or "",
                "reasonText":  r.reason_text or "",
                "contentHash": r.content_hash or "",
                "tenantId":    r.tenant_id or "",
                "timestamp":   r.signed_at.isoformat() if r.signed_at else "",
                "prevHash":    r.prev_hash or "",
                "rowHash":     r.row_hash or "",
            } for r in rows]
    except Exception:
        log.exception("esignature.chain_verify_failed")
        return {"ok": False, "checked": 0, "broken_at": None, "error": "db_unavailable"}

    prev = ""
    for snap in snapshots:
        entry = {k: snap[k] for k in (
            "entityType", "entityId", "action", "meaning", "signer", "role",
            "reasonCode", "reasonText", "contentHash", "tenantId", "timestamp")}
        expected = chain_next(prev, entry)
        if snap["prevHash"] != prev or snap["rowHash"] != expected:
            return {"ok": False, "checked": len(snapshots), "broken_at": snap["id"]}
        prev = expected
    return {"ok": True, "checked": len(snapshots), "broken_at": None}
