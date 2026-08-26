"""21 CFR Part 11 audit trail.

Every regulated action (record status change, CAPA approval, login, role
change, agent workflow) writes one immutable, hash-chained row to
``qms_audit_log``. If the DB is not reachable, we fall back to an
atomically-written JSON file with the chain preserved.

Reads and chain-verification helpers live here so callers never touch the
raw SQLAlchemy model.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from services.logging_config import get_logger
from services.security import chain_next

_logger = get_logger(__name__)

_AUDIT_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "audit_log.json")
)
_FILE_LOCK = threading.Lock()
_CHAIN_LOCK = threading.Lock()  # coarse lock around the DB "latest hash" read

# Actions
ACTION_RECORD_STATUS_CHANGE = "record_status_change"
ACTION_CAPA_GENERATED       = "capa_generated"
ACTION_CAPA_SAVED           = "capa_saved"
ACTION_CAPA_STATUS_CHANGE   = "capa_status_change"
ACTION_CAPA_BATCH_RUN       = "capa_batch_run"
ACTION_RECORD_UPLOADED      = "record_uploaded"
ACTION_RECORD_EXTRACTED     = "record_extracted"
ACTION_USER_LOGIN           = "user_login"
ACTION_USER_LOGOUT          = "user_logout"
ACTION_USER_APPROVED        = "user_approved"
ACTION_USER_REJECTED        = "user_rejected"
ACTION_ROLE_CHANGED         = "role_changed"
ACTION_SEARCH_PERFORMED     = "search_performed"
ACTION_AGENT_EVENT          = "agent_event"


@contextmanager
def _session():
    """Yield a SQLAlchemy session using the root database module."""
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_entry(
    *,
    action: str,
    performed_by: str,
    performed_by_role: str,
    record_id: Optional[str],
    capa_id: Optional[str],
    entity_type: str,
    old_value: Optional[str],
    new_value: Optional[str],
    field_name: Optional[str],
    notes: Optional[str],
    ip_address: Optional[str],
    user_agent: Optional[str],
    payload: Optional[dict],
) -> dict:
    return {
        "timestamp":        _now_iso(),
        "action":           action,
        "entityType":       entity_type,
        "recordId":         record_id,
        "capaId":           capa_id,
        "performedBy":      performed_by,
        "performedByRole":  performed_by_role,
        "oldValue":         old_value,
        "newValue":         new_value,
        "fieldName":        field_name,
        "notes":            notes,
        "ipAddress":        ip_address,
        "userAgent":        user_agent,
        "payload":          payload or {},
    }


def log(
    action: str,
    performed_by: str,
    performed_by_role: str = "",
    record_id: Optional[str] = None,
    capa_id: Optional[str] = None,
    entity_type: str = "record",
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    field_name: Optional[str] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    payload: Optional[dict] = None,
) -> dict:
    """Persist one immutable, hash-chained audit entry.

    Returns the stored row as a dict (including ``rowHash`` and ``prevHash``).
    """
    entry = _build_entry(
        action=action,
        performed_by=performed_by,
        performed_by_role=performed_by_role,
        record_id=record_id,
        capa_id=capa_id,
        entity_type=entity_type,
        old_value=old_value,
        new_value=new_value,
        field_name=field_name,
        notes=notes,
        ip_address=ip_address,
        user_agent=user_agent,
        payload=payload,
    )

    try:
        return _log_to_db(entry)
    except Exception:
        _logger.exception("audit.db_write_failed_falling_back", extra={"action": action})
        return _log_to_json(entry)


# ── DB backend ────────────────────────────────────────────
def _log_to_db(entry: dict) -> dict:
    from models import AuditLog

    with _CHAIN_LOCK, _session() as session:
        last = (
            session.query(AuditLog)
            .order_by(AuditLog.id.desc())
            .limit(1)
            .one_or_none()
        )
        prev_hash = (last.row_hash or "") if last else ""
        row_hash = chain_next(prev_hash, entry)

        row = AuditLog(
            timestamp=datetime.utcnow(),
            record_id=entry.get("recordId"),
            capa_id=entry.get("capaId"),
            entity_type=entry.get("entityType") or "record",
            action=entry["action"],
            old_value=_stringify(entry.get("oldValue")),
            new_value=_stringify(entry.get("newValue")),
            field_name=entry.get("fieldName"),
            performed_by=entry["performedBy"] or "system",
            performed_by_role=entry.get("performedByRole") or "",
            ip_address=entry.get("ipAddress"),
            user_agent=entry.get("userAgent"),
            notes=entry.get("notes"),
            payload=entry.get("payload") or {},
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
        session.add(row)
        session.flush()
        return row.to_dict()


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


# ── JSON fallback (dev / degraded mode) ───────────────────
def _log_to_json(entry: dict) -> dict:
    with _FILE_LOCK:
        entries = _load_json()
        prev_hash = entries[-1].get("rowHash", "") if entries else ""
        row_hash = chain_next(prev_hash, entry)
        entry["prevHash"] = prev_hash
        entry["rowHash"] = row_hash
        entries.append(entry)
        # Cap at 100k entries — well beyond usable dev volume, still bounded.
        if len(entries) > 100_000:
            entries = entries[-100_000:]
        _atomic_write_json(entries)
    return entry


def _load_json() -> list:
    if not os.path.exists(_AUDIT_FILE):
        return []
    try:
        with open(_AUDIT_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        _logger.exception("audit.json_load_failed")
        return []


def _atomic_write_json(entries: list) -> None:
    tmp = f"{_AUDIT_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, default=str)
    os.replace(tmp, _AUDIT_FILE)


# ── Reads ─────────────────────────────────────────────────
def get_audit_trail(
    record_id: Optional[str] = None,
    capa_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 100,
) -> list:
    try:
        return _get_from_db(record_id, capa_id, entity_type, limit)
    except Exception:
        _logger.exception("audit.db_read_failed_falling_back")
        return _get_from_json(record_id, capa_id, entity_type, limit)


def get_recent_activity(limit: int = 50) -> list:
    return get_audit_trail(limit=limit)


def _get_from_db(record_id, capa_id, entity_type, limit) -> list:
    from models import AuditLog
    from sqlalchemy import desc

    with _session() as session:
        q = session.query(AuditLog)
        if record_id:
            q = q.filter(AuditLog.record_id == record_id)
        if capa_id:
            q = q.filter(AuditLog.capa_id == capa_id)
        if entity_type:
            q = q.filter(AuditLog.entity_type == entity_type)
        rows = q.order_by(desc(AuditLog.timestamp)).limit(max(1, min(limit, 1000))).all()
        return [r.to_dict() for r in rows]


def _get_from_json(record_id, capa_id, entity_type, limit) -> list:
    entries = _load_json()
    if record_id:
        entries = [e for e in entries if e.get("recordId") == record_id]
    if capa_id:
        entries = [e for e in entries if e.get("capaId") == capa_id]
    if entity_type:
        entries = [e for e in entries if e.get("entityType") == entity_type]
    return list(reversed(entries))[:limit]


# ── Chain verification ────────────────────────────────────
def verify_audit_chain(limit: int = 1000) -> dict:
    """Recompute the hash chain over the newest ``limit`` rows.

    Returns ``{"ok": bool, "checked": int, "broken_at": Optional[int]}``.
    Callers can use this in a scheduled job to prove tamper-evidence.
    """
    try:
        from models import AuditLog

        with _session() as session:
            rows = (
                session.query(AuditLog)
                .order_by(AuditLog.id.asc())
                .limit(limit)
                .all()
            )
    except Exception:
        _logger.exception("audit.chain_verify_db_failed")
        return {"ok": False, "checked": 0, "broken_at": None, "error": "db_unavailable"}

    prev = ""
    for row in rows:
        # Rebuild the entry payload from stored columns (mirrors _build_entry).
        entry = {
            "timestamp": row.timestamp.isoformat() if row.timestamp else "",
            "action": row.action,
            "entityType": row.entity_type,
            "recordId": row.record_id,
            "capaId": row.capa_id,
            "performedBy": row.performed_by,
            "performedByRole": row.performed_by_role,
            "oldValue": row.old_value,
            "newValue": row.new_value,
            "fieldName": row.field_name,
            "notes": row.notes,
            "ipAddress": row.ip_address,
            "userAgent": row.user_agent,
            "payload": row.payload or {},
        }
        expected = chain_next(prev, entry)
        if (row.prev_hash or "") != prev or (row.row_hash or "") != expected:
            return {"ok": False, "checked": len(rows), "broken_at": row.id}
        prev = expected
    return {"ok": True, "checked": len(rows), "broken_at": None}
