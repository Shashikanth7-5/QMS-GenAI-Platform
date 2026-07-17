from services.agents.admin_access_agent import AdminAccessAgent
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

    def run(self, record_id: str) -> dict:
        intake = self.intake.run(record_id)
        if intake.status == "error":
            return {"status": "error", "steps": [intake.to_dict()]}

        record = intake.data["record"]
        decision = self.decision.run(record)
        rca = self.rca.run(record)
        draft = None
        if decision.data["decision"].get("capa_triggered"):
            draft = self.capa.run(record, decision.data["decision"], rca.data["score"])

        steps = [intake.to_dict(), decision.to_dict(), rca.to_dict()]
        if draft:
            steps.append(draft.to_dict())

        return {
            "status": "ok",
            "recordId": record_id,
            "capaTriggered": decision.data["decision"].get("capa_triggered", False),
            "requiresHumanApproval": True,
            "steps": steps,
            "draft": draft.to_dict()["data"]["capa"] if draft else None,
        }


def run_access_review() -> dict:
    return AdminAccessAgent().run().to_dict()
