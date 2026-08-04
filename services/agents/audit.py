import json
import os
import threading
from datetime import datetime, timezone
from typing import Optional


_AGENT_AUDIT_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "agent_audit_log.json")
)
_LOCK = threading.Lock()


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
    """Append an immutable operational event for agent observability."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runId": run_id,
        "agent": agent,
        "event": event,
        "status": status,
        "recordId": record_id,
        "capaId": capa_id,
        "triggeredBy": triggered_by,
        "durationMs": duration_ms,
        "details": details or {},
    }
    with _LOCK:
        entries = _load_events()
        entries.append(entry)
        entries = entries[-10000:]
        with open(_AGENT_AUDIT_FILE, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2, default=str)
    return entry


def get_agent_events(
    limit: int = 100,
    *,
    status: Optional[str] = None,
    agent: Optional[str] = None,
    record_id: Optional[str] = None,
) -> list:
    entries = _load_events()
    if status:
        entries = [item for item in entries if item.get("status") == status]
    if agent:
        entries = [item for item in entries if item.get("agent") == agent]
    if record_id:
        entries = [item for item in entries if item.get("recordId") == record_id]
    return list(reversed(entries))[:max(1, min(limit, 1000))]


def _load_events() -> list:
    if not os.path.exists(_AGENT_AUDIT_FILE):
        return []
    try:
        with open(_AGENT_AUDIT_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []
