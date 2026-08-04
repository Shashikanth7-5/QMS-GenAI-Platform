import os
import random
import time
import uuid
from datetime import datetime

from data.records import get_all_capas, save_capa, update_record_status
from services.agents.admin_access_agent import AdminAccessAgent
from services.agents.audit import log_agent_event
from services.agents.capa_draft_agent import CAPADraftAgent
from services.agents.decision_agent import DecisionEligibilityAgent
from services.agents.rca_scoring_agent import RCAScoringAgent
from services.agents.record_intake_agent import RecordIntakeAgent


class CapaAgentOrchestrator:
    def __init__(self):
        self.intake = RecordIntakeAgent()
        self.decision = DecisionEligibilityAgent()
        self.rca = RCAScoringAgent()
        self.capa = CAPADraftAgent()

    def run(
        self,
        record_id: str,
        *,
        triggered_by: str = "manual",
        save_draft: bool = False,
        parent_run_id: str = None,
    ) -> dict:
        run_id = parent_run_id or f"RUN-{uuid.uuid4().hex[:12].upper()}"
        started = time.perf_counter()
        log_agent_event(
            "capa_agent_orchestrator", "workflow_started", "running",
            run_id=run_id, record_id=record_id, triggered_by=triggered_by,
        )
        intake = self.intake.run(record_id)
        if intake.status == "error":
            log_agent_event(
                self.intake.name, "record_intake", "error", run_id=run_id,
                record_id=record_id, triggered_by=triggered_by,
                details={"summary": intake.summary},
            )
            return {"status": "error", "error": intake.summary, "agentRunId": run_id,
                    "steps": [intake.to_dict()]}

        record = intake.data["record"]
        self._log_step(intake, "record_intake", run_id, record_id, triggered_by)
        decision = self.decision.run(record)
        self._log_step(decision, "eligibility_decision", run_id, record_id, triggered_by)
        rca = self.rca.run(record)
        self._log_step(rca, "rca_scoring", run_id, record_id, triggered_by)
        draft = None
        saved_capa = None
        if decision.data["decision"].get("capa_triggered"):
            draft = self.capa.run(record, decision.data["decision"], rca.data["score"])
            self._log_step(draft, "capa_draft", run_id, record_id, triggered_by)
            if save_draft:
                saved_capa = self._save_draft(record, draft.data["capa"])
                log_agent_event(
                    self.capa.name, "capa_saved_for_review", "ok", run_id=run_id,
                    record_id=record_id, capa_id=saved_capa["capaId"],
                    triggered_by=triggered_by,
                    details={"status": "Under Review", "requiresHumanApproval": True},
                )

        steps = [intake.to_dict(), decision.to_dict(), rca.to_dict()]
        if draft:
            steps.append(draft.to_dict())

        result = {
            "status": "ok",
            "agentRunId": run_id,
            "recordId": record_id,
            "capaTriggered": decision.data["decision"].get("capa_triggered", False),
            "requiresHumanApproval": True,
            "steps": steps,
            "draft": draft.to_dict()["data"]["capa"] if draft else None,
            "savedCapa": saved_capa,
        }
        log_agent_event(
            "capa_agent_orchestrator", "workflow_completed", "ok", run_id=run_id,
            record_id=record_id, capa_id=saved_capa.get("capaId") if saved_capa else None,
            triggered_by=triggered_by,
            duration_ms=int((time.perf_counter() - started) * 1000),
            details={"capaTriggered": result["capaTriggered"],
                     "draftSaved": bool(saved_capa), "humanApprovalRequired": True},
        )
        return result

    @staticmethod
    def _log_step(result, event, run_id, record_id, triggered_by):
        details = {"summary": result.summary, "warnings": result.warnings}
        if event == "eligibility_decision":
            details["decision"] = result.data.get("decision", {})
        elif event == "rca_scoring":
            details["score"] = result.data.get("score", {})
        elif event == "capa_draft":
            details["llm"] = {
                "provider": os.getenv("AI_PROVIDER", "mock"),
                "model": os.getenv("AI_MODEL", "mock-mode"),
                "inputFields": ["title", "description", "priority", "sector", "site"],
            }
        log_agent_event(
            result.agent, event, result.status, run_id=run_id,
            record_id=record_id, triggered_by=triggered_by, details=details,
        )

    @staticmethod
    def _save_draft(record: dict, draft: dict) -> dict:
        existing = next(
            (c for c in get_all_capas() if c.get("sourceRecordId") == record.get("id")),
            None,
        )
        if existing:
            return {"capaId": existing["capaId"], "recordId": record["id"],
                    "status": existing["status"], "created": False}

        capa_id = f"CAPA-{datetime.now().year}-{random.randint(1000, 9999)}"
        payload = {
            **draft,
            "capaId": capa_id,
            "sourceRecordId": record["id"],
            "status": "Under Review",
            "capaOwner": draft.get("capaOwner") or draft.get("proposedOwner", ""),
            "createdByUsername": "responsible-ai-agent",
        }
        saved = save_capa(payload)
        update_record_status(record["id"], "Under Review")
        try:
            from services.vector_store import embed_capa
            embed_capa(payload)
        except Exception as exc:
            print(f"[agents] vector embed skipped: {exc}")
        return {"capaId": saved.get("capaId", capa_id), "recordId": record["id"],
                "status": "Under Review", "created": True}


def run_access_review() -> dict:
    return AdminAccessAgent().run().to_dict()
