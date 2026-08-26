"""Durable dead-letter queue for the agent supervisor.

Previously supervisor.py used a module-level list — anything in the queue
was wiped on worker restart, which made ops impossible in production.
This module stores dead-lettered records in the ``qms_agent_deadletter``
table and offers a small in-memory fallback for local dev when the DB
schema is not yet created.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

from services.logging_config import get_logger

log = get_logger(__name__)

# In-memory fallback (only used when DB writes fail — e.g. schema not migrated).
_MEMORY_FALLBACK: list[dict] = []
_MEMORY_LOCK = Lock()


def _db_session():
    from database import SessionLocal
    return SessionLocal()


def park(
    record_id: str,
    *,
    attempts: int,
    last_error: str,
    run_id: str,
    tenant_id: Optional[str] = None,
    max_retention: int = 500,
) -> dict:
    """Persist a dead-letter entry. Returns the row as a dict."""
    try:
        from models import AgentDeadLetter
        with _db_session() as session:
            entry = AgentDeadLetter(
                record_id=record_id,
                run_id=run_id,
                attempts=attempts,
                last_error=(last_error or "")[:2000],
                tenant_id=tenant_id,
            )
            session.add(entry)
            # Keep at most `max_retention` un-requeued rows.
            excess = session.query(AgentDeadLetter).filter(
                AgentDeadLetter.requeued_at.is_(None),
            ).count() - max_retention
            if excess > 0:
                stale = (
                    session.query(AgentDeadLetter)
                    .filter(AgentDeadLetter.requeued_at.is_(None))
                    .order_by(AgentDeadLetter.parked_at.asc())
                    .limit(excess)
                    .all()
                )
                for row in stale:
                    session.delete(row)
            session.commit()
            return entry.to_dict()
    except Exception:
        log.warning("deadletter.db_park_failed_memory_fallback", exc_info=True,
                    extra={"record_id": record_id})
        with _MEMORY_LOCK:
            entry = {
                "recordId": record_id,
                "attempts": attempts,
                "lastError": last_error or "",
                "runId": run_id,
                "tenantId": tenant_id or "",
                "parkedAt": datetime.utcnow().isoformat() + "Z",
            }
            _MEMORY_FALLBACK.append(entry)
            if len(_MEMORY_FALLBACK) > max_retention:
                del _MEMORY_FALLBACK[: len(_MEMORY_FALLBACK) - max_retention]
            return entry


def list_active(*, tenant_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    try:
        from models import AgentDeadLetter
        with _db_session() as session:
            q = session.query(AgentDeadLetter).filter(AgentDeadLetter.requeued_at.is_(None))
            if tenant_id:
                q = q.filter(AgentDeadLetter.tenant_id == tenant_id)
            rows = q.order_by(AgentDeadLetter.parked_at.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]
    except Exception:
        log.warning("deadletter.db_list_failed_memory_fallback", exc_info=True)
        with _MEMORY_LOCK:
            return list(_MEMORY_FALLBACK)


def requeue(record_id: str, *, requeued_by: str = "system") -> bool:
    """Mark a dead-letter row as requeued. Returns True if a row was updated."""
    try:
        from models import AgentDeadLetter
        with _db_session() as session:
            row = (
                session.query(AgentDeadLetter)
                .filter(
                    AgentDeadLetter.record_id == record_id,
                    AgentDeadLetter.requeued_at.is_(None),
                )
                .order_by(AgentDeadLetter.parked_at.desc())
                .first()
            )
            if not row:
                return False
            row.requeued_at = datetime.utcnow()
            row.requeued_by = requeued_by
            session.commit()
            return True
    except Exception:
        log.warning("deadletter.db_requeue_failed_memory_fallback", exc_info=True,
                    extra={"record_id": record_id})
        with _MEMORY_LOCK:
            for i, entry in enumerate(_MEMORY_FALLBACK):
                if entry.get("recordId") == record_id:
                    del _MEMORY_FALLBACK[i]
                    return True
            return False


def is_dead_lettered(record_id: str) -> bool:
    """Cheap check used by the supervisor's eligibility scan."""
    try:
        from models import AgentDeadLetter
        with _db_session() as session:
            row = (
                session.query(AgentDeadLetter.id)
                .filter(
                    AgentDeadLetter.record_id == record_id,
                    AgentDeadLetter.requeued_at.is_(None),
                )
                .first()
            )
            return row is not None
    except Exception:
        with _MEMORY_LOCK:
            return any(e.get("recordId") == record_id for e in _MEMORY_FALLBACK)


def prune_expired(*, max_age_days: int = 30) -> int:
    """Delete requeued/older-than-max_age rows. Callable from a Celery beat task."""
    try:
        from models import AgentDeadLetter
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        with _db_session() as session:
            deleted = (
                session.query(AgentDeadLetter)
                .filter(AgentDeadLetter.parked_at < cutoff)
                .delete()
            )
            session.commit()
            return int(deleted or 0)
    except Exception:
        log.warning("deadletter.db_prune_failed", exc_info=True)
        return 0
