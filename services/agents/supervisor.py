"""Agent supervisor.

Scans for eligible records and dispatches each to the CAPA
orchestrator. Failures are retried up to ``AGENT_MAX_RETRIES`` times
per record, then parked in an in-memory dead-letter queue so they
stop consuming turn budget forever. The queue is exposed via
``get_supervisor_status()`` so admins can inspect and requeue.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from config import (
    AGENT_AUTOSAVE_CAPA_DRAFT,
    AGENT_DEADLETTER_MAX,
    AGENT_KILL_SWITCH,
    AGENT_MAX_RETRIES,
)
from data.records import get_all_capas, get_all_records
from services.agents import deadletter_store
from services.agents.audit import get_agent_events, log_agent_event
from services.agents.notifications import send_agent_alert
from services.agents.orchestrator import CapaAgentOrchestrator
from services.logging_config import get_logger

log = get_logger(__name__)

# In-memory attempt counter (per-worker). Persisting this to DB is overkill —
# supervisor runs every 20 min and a lost worker just resets the counter,
# giving the record another chance.
_ATTEMPT_COUNTS: dict[str, int] = {}


def _record_attempt(record_id: str) -> int:
    _ATTEMPT_COUNTS[record_id] = _ATTEMPT_COUNTS.get(record_id, 0) + 1
    return _ATTEMPT_COUNTS[record_id]


def _clear_attempts(record_id: str) -> None:
    _ATTEMPT_COUNTS.pop(record_id, None)


def get_dead_letters() -> list[dict]:
    return deadletter_store.list_active(limit=AGENT_DEADLETTER_MAX)


def requeue_dead_letter(record_id: str, *, requeued_by: str = "system") -> bool:
    ok = deadletter_store.requeue(record_id, requeued_by=requeued_by)
    if ok:
        _clear_attempts(record_id)
    return ok


class AgentSupervisor:
    name = "responsible_ai_supervisor"

    @staticmethod
    def is_weekend(now=None) -> bool:
        return (now or datetime.now()).weekday() >= 5

    @staticmethod
    def eligible_records() -> list:
        existing = {c.get("sourceRecordId") for c in get_all_capas()}
        candidates = [
            record for record in get_all_records()
            if record.get("status") == "Draft Generated"
            and record.get("id") not in existing
        ]
        # Filter out dead-lettered records via the persistent store.
        return [r for r in candidates if not deadletter_store.is_dead_lettered(r.get("id"))]

    def run_once(self, *, triggered_by="system", limit=50, allow_weekend=False) -> dict:
        run_id = f"SUP-{uuid.uuid4().hex[:12].upper()}"

        if AGENT_KILL_SWITCH:
            log_agent_event(
                self.name, "scan_skipped", "skipped", run_id=run_id,
                triggered_by=triggered_by, details={"reason": "kill_switch"},
            )
            return {"status": "skipped", "reason": "kill_switch", "runId": run_id}

        if self.is_weekend() and not allow_weekend:
            log_agent_event(
                self.name, "scan_skipped", "skipped", run_id=run_id,
                triggered_by=triggered_by, details={"reason": "weekend"},
            )
            return {"status": "skipped", "reason": "weekend", "runId": run_id}

        records = self.eligible_records()[:max(1, min(int(limit), 200))]
        log_agent_event(
            self.name, "scan_started", "running", run_id=run_id,
            triggered_by=triggered_by,
            details={
                "eligibleRecords": len(records),
                "autosave": AGENT_AUTOSAVE_CAPA_DRAFT,
            },
        )
        processed, proposed, not_eligible, errors, dead_letters = [], [], [], [], []

        for record in records:
            record_id = record.get("id")
            attempts = _record_attempt(record_id)
            try:
                result = CapaAgentOrchestrator().run(
                    record_id, triggered_by=triggered_by,
                    save_draft=AGENT_AUTOSAVE_CAPA_DRAFT,
                    parent_run_id=run_id,
                )
                if result.get("status") == "error":
                    if attempts >= AGENT_MAX_RETRIES:
                        entry = deadletter_store.park(
                            record_id,
                            attempts=attempts,
                            last_error=result.get("error") or "",
                            run_id=run_id,
                        )
                        dead_letters.append(entry)
                        log_agent_event(
                            self.name, "record_dead_lettered", "error",
                            run_id=run_id, record_id=record_id,
                            triggered_by=triggered_by, details=entry,
                        )
                    else:
                        errors.append({"recordId": record_id, "error": result.get("error"),
                                       "attempts": attempts})
                elif result.get("savedCapa"):
                    processed.append(result["savedCapa"])
                    _clear_attempts(record_id)
                elif result.get("capaTriggered") and result.get("draft"):
                    # Draft prepared but autosave is disabled — record it as a
                    # proposal awaiting human approval.
                    proposed.append({
                        "recordId": record_id,
                        "draft": result["draft"],
                        "agentRunId": result.get("agentRunId"),
                    })
                    _clear_attempts(record_id)
                else:
                    not_eligible.append(record_id)
                    _clear_attempts(record_id)
            except Exception as exc:
                log.exception("agent.supervisor.record_failed",
                              extra={"record_id": record_id, "attempts": attempts})
                if attempts >= AGENT_MAX_RETRIES:
                    entry = deadletter_store.park(
                        record_id,
                        attempts=attempts,
                        last_error=str(exc),
                        run_id=run_id,
                    )
                    dead_letters.append(entry)
                else:
                    errors.append({"recordId": record_id, "error": str(exc),
                                   "attempts": attempts})

        status = "error" if (errors or dead_letters) and not processed and not proposed else \
                 "warning" if (errors or dead_letters) else "ok"
        summary = {
            "status": status,
            "runId": run_id,
            "eligible": len(records),
            "processed": len(processed),
            "proposed": len(proposed),
            "notEligible": len(not_eligible),
            "errors": len(errors),
            "deadLettered": len(dead_letters),
            "autosave": AGENT_AUTOSAVE_CAPA_DRAFT,
            "capas": processed,
            "proposals": proposed,
            "errorDetails": errors,
            "deadLetterDetails": dead_letters,
        }
        log_agent_event(
            self.name, "scan_completed", status, run_id=run_id,
            triggered_by=triggered_by, details=summary,
        )
        if errors or dead_letters:
            send_agent_alert(
                "QMS agent supervisor completed with errors",
                f"Agent run {run_id}: {len(errors)} retryable error(s), "
                f"{len(dead_letters)} dead-lettered record(s).",
                run_id=run_id, details={"errors": errors, "deadLetters": dead_letters},
            )
        return summary


def get_supervisor_status() -> dict:
    events = get_agent_events(limit=500)
    latest_completion = next(
        (event for event in events if event.get("agent") == AgentSupervisor.name
         and event.get("event") in {"scan_completed", "scan_skipped"}),
        None,
    )
    active = [event for event in events if event.get("status") == "running"]
    alerts = [event for event in events if event.get("status") in {"alert", "error"}][:20]
    return {
        "agent": AgentSupervisor.name,
        "schedule": "Every 20 minutes, Monday-Friday",
        "latestRun": latest_completion,
        "activeRuns": active[:20],
        "alerts": alerts,
        "pendingRecords": len(AgentSupervisor.eligible_records()),
        "deadLetterQueue": get_dead_letters(),
        "killSwitchActive": AGENT_KILL_SWITCH,
    }
