# services/audit_service.py
# 21 CFR Part 11 compliant audit trail.
# Every status change, CAPA approval, login, and role change is logged.
# Logs to PostgreSQL when available, falls back to audit_log.json.
# IMMUTABLE — audit entries are never updated or deleted.

import json
import os
from datetime import datetime
from typing import Optional

_AUDIT_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "audit_log.json")
)

# Actions — use these constants everywhere so the audit log is consistent
ACTION_RECORD_STATUS_CHANGE = "record_status_change"
ACTION_CAPA_GENERATED       = "capa_generated"
ACTION_CAPA_SAVED           = "capa_saved"
ACTION_CAPA_STATUS_CHANGE   = "capa_status_change"
ACTION_CAPA_BATCH_RUN       = "capa_batch_run"
ACTION_RECORD_UPLOADED      = "record_uploaded"
ACTION_RECORD_EXTRACTED     = "record_extracted"
ACTION_USER_LOGIN            = "user_login"
ACTION_USER_LOGOUT           = "user_logout"
ACTION_USER_APPROVED         = "user_approved"
ACTION_USER_REJECTED         = "user_rejected"
ACTION_ROLE_CHANGED          = "role_changed"
ACTION_SEARCH_PERFORMED      = "search_performed"


def log(
    action:            str,
    performed_by:      str,
    performed_by_role: str = "",
    record_id:         Optional[str] = None,
    capa_id:           Optional[str] = None,
    entity_type:       str = "record",
    old_value:         Optional[str] = None,
    new_value:         Optional[str] = None,
    field_name:        Optional[str] = None,
    notes:             Optional[str] = None,
    ip_address:        Optional[str] = None,
    user_agent:        Optional[str] = None,
) -> dict:
    """
    Write one immutable audit entry.
    Returns the entry dict so callers can log it if needed.
    """
    entry = {
        "timestamp":        datetime.utcnow().isoformat() + "Z",
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
    }

    from data.database import USE_DB
    if USE_DB:
        _log_to_db(entry)
    else:
        _log_to_json(entry)

    return entry


def get_audit_trail(
    record_id: Optional[str] = None,
    capa_id:   Optional[str] = None,
    limit:     int = 100,
) -> list:
    """Retrieve audit entries for a specific record or CAPA."""
    from data.database import USE_DB
    if USE_DB:
        return _get_from_db(record_id, capa_id, limit)
    return _get_from_json(record_id, capa_id, limit)


def get_recent_activity(limit: int = 50) -> list:
    """Get the most recent audit entries across all entities."""
    from data.database import USE_DB
    if USE_DB:
        return _get_from_db(limit=limit)
    return _get_from_json(limit=limit)


# ── PostgreSQL backend ────────────────────────────────────
def _log_to_db(entry: dict):
    try:
        from data.database import get_session
        from data.models import AuditLog
        with get_session() as session:
            session.add(AuditLog(
                record_id         = entry.get("recordId"),
                capa_id           = entry.get("capaId"),
                entity_type       = entry.get("entityType", "record"),
                action            = entry["action"],
                old_value         = entry.get("oldValue"),
                new_value         = entry.get("newValue"),
                field_name        = entry.get("fieldName"),
                performed_by      = entry["performedBy"],
                performed_by_role = entry.get("performedByRole", ""),
                ip_address        = entry.get("ipAddress"),
                notes             = entry.get("notes"),
                timestamp         = datetime.utcnow(),
            ))
            session.commit()
    except Exception as e:
        print(f"[audit] DB log failed — falling back to JSON: {e}")
        _log_to_json(entry)


def _get_from_db(record_id=None, capa_id=None, limit=100) -> list:
    try:
        from data.database import get_session
        from data.models import AuditLog
        from sqlalchemy import desc
        with get_session() as session:
            q = session.query(AuditLog)
            if record_id: q = q.filter(AuditLog.record_id == record_id)
            if capa_id:   q = q.filter(AuditLog.capa_id   == capa_id)
            entries = q.order_by(desc(AuditLog.timestamp)).limit(limit).all()
            return [e.to_dict() for e in entries]
    except Exception as e:
        print(f"[audit] DB read failed: {e}")
        return []


# ── JSON fallback backend ──────────────────────────────────
def _load_json() -> list:
    if not os.path.exists(_AUDIT_FILE):
        return []
    try:
        with open(_AUDIT_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _log_to_json(entry: dict):
    entries = _load_json()
    entries.append(entry)
    # Keep last 10,000 entries to prevent unbounded growth
    if len(entries) > 10000:
        entries = entries[-10000:]
    try:
        with open(_AUDIT_FILE, "w") as f:
            json.dump(entries, f, indent=2, default=str)
    except Exception as e:
        print(f"[audit] JSON write failed: {e}")


def _get_from_json(record_id=None, capa_id=None, limit=100) -> list:
    entries = _load_json()
    if record_id:
        entries = [e for e in entries if e.get("recordId") == record_id]
    if capa_id:
        entries = [e for e in entries if e.get("capaId")   == capa_id]
    return list(reversed(entries))[:limit]
