import uuid
from datetime import datetime

from data.records import get_all_capas, get_all_records
from services.agents.audit import get_agent_events, log_agent_event
from services.agents.notifications import send_agent_alert
from services.agents.orchestrator import CapaAgentOrchestrator


class AgentSupervisor:
    name = "responsible_ai_supervisor"

    @staticmethod
    def is_weekend(now=None) -> bool:
        return (now or datetime.now()).weekday() >= 5

    @staticmethod
    def eligible_records() -> list:
        existing = {c.get("sourceRecordId") for c in get_all_capas()}
        return [
            record for record in get_all_records()
            if record.get("status") == "Draft Generated"
            and record.get("id") not in existing
        ]

    def run_once(self, *, triggered_by="system", limit=50, allow_weekend=False) -> dict:
        run_id = f"SUP-{uuid.uuid4().hex[:12].upper()}"
        if self.is_weekend() and not allow_weekend:
            log_agent_event(
                self.name, "scan_skipped", "skipped", run_id=run_id,
                triggered_by=triggered_by, details={"reason": "weekend"},
            )
            return {"status": "skipped", "reason": "weekend", "runId": run_id}

        records = self.eligible_records()[:max(1, min(int(limit), 200))]
        log_agent_event(
            self.name, "scan_started", "running", run_id=run_id,
            triggered_by=triggered_by, details={"eligibleRecords": len(records)},
        )
        processed, not_eligible, errors = [], [], []
        for record in records:
            try:
                result = CapaAgentOrchestrator().run(
                    record["id"], triggered_by=triggered_by, save_draft=True,
                    parent_run_id=run_id,
                )
                if result.get("status") == "error":
                    errors.append({"recordId": record["id"], "error": result.get("error")})
                elif result.get("savedCapa"):
                    processed.append(result["savedCapa"])
                else:
                    not_eligible.append(record["id"])
            except Exception as exc:
                errors.append({"recordId": record["id"], "error": str(exc)})

        status = "error" if errors and not processed else "warning" if errors else "ok"
        summary = {
            "status": status,
            "runId": run_id,
            "eligible": len(records),
            "processed": len(processed),
            "notEligible": len(not_eligible),
            "errors": len(errors),
            "capas": processed,
            "errorDetails": errors,
        }
        log_agent_event(
            self.name, "scan_completed", status, run_id=run_id,
            triggered_by=triggered_by, details=summary,
        )
        if errors:
            send_agent_alert(
                "QMS agent supervisor completed with errors",
                f"Agent run {run_id} had {len(errors)} error(s).",
                run_id=run_id, details={"errors": errors},
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
    }
