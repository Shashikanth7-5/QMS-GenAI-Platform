"""Agent event audit trail — persists to the same qms_audit_log table
as the regulated CAPA/record audit, but with entity_type='agent'.

Keeps the same public API (``log_agent_event``, ``get_agent_events``)
so existing callers keep working. Under the hood every write goes
through ``services.audit_service`` and inherits its hash chain, atomic
JSON fallback, and DB persistence.
"""

from __future__ import annotations

from typing import Optional

from services import audit_service
from services.logging_config import get_logger

_logger = get_logger(__name__)

_ENTITY = "agent"


def log_agent_event(
    agent: str,
    event: str,
    status: str,
    *,
    run_id: str,
    record_id: Optional[str] = None,
    capa_id: Optional[str] = None,
    triggered_by: str = "system",
    duration_ms: Optional[int] = None,
    details: Optional[dict] = None,
) -> dict:
    """Append one agent operational event to the audit trail."""
    payload = {
        "runId": run_id,
        "agent": agent,
        "event": event,
        "status": status,
        "durationMs": duration_ms,
        "details": details or {},
    }
    action = f"agent:{event}"
    row = audit_service.log(
        action=action,
        performed_by=triggered_by or "system",
        performed_by_role="agent",
        record_id=record_id,
        capa_id=capa_id,
        entity_type=_ENTITY,
        notes=f"{agent} {event} -> {status}",
        payload=payload,
    )
    _logger.info(
        "agent.event",
        extra={
            "agent": agent,
            "event": event,
            "status": status,
            "run_id": run_id,
            "record_id": record_id,
            "capa_id": capa_id,
        },
    )
    # Return a dict shaped like the old contract so existing callers keep working.
    return {
        "timestamp": row.get("timestamp"),
        "runId": run_id,
        "agent": agent,
        "event": event,
        "status": status,
        "recordId": record_id,
        "capaId": capa_id,
        "triggeredBy": triggered_by,
        "durationMs": duration_ms,
        "details": details or {},
        "rowHash": row.get("rowHash"),
    }


def get_agent_events(
    limit: int = 100,
    *,
    status: Optional[str] = None,
    agent: Optional[str] = None,
    record_id: Optional[str] = None,
) -> list:
    rows = audit_service.get_audit_trail(
        record_id=record_id,
        entity_type=_ENTITY,
        limit=max(1, min(limit, 1000)),
    )
    events = []
    for row in rows:
        payload = row.get("payload") or {}
        if status and payload.get("status") != status:
            continue
        if agent and payload.get("agent") != agent:
            continue
        events.append({
            "timestamp": row.get("timestamp"),
            "runId": payload.get("runId"),
            "agent": payload.get("agent"),
            "event": payload.get("event"),
            "status": payload.get("status"),
            "recordId": row.get("recordId"),
            "capaId": row.get("capaId"),
            "triggeredBy": row.get("performedBy"),
            "durationMs": payload.get("durationMs"),
            "details": payload.get("details") or {},
            "rowHash": row.get("rowHash"),
        })
    return events
