from services.agents.base import AgentResult


class CAPADraftAgent:
    name = "capa_draft_agent"

    def run(self, record: dict, decision: dict, rca_score: dict) -> AgentResult:
        from services.ai_service import generate_capa
        from services.guardrails import validate_capa

        capa = generate_capa(record)
        capa["sourceRecordId"] = record.get("id", "")
        capa["agentDecision"] = decision
        capa["rcaQualityScore"] = rca_score.get("overall_score")
        is_valid, warnings = validate_capa(capa)
        status = "ok" if is_valid else "warning"
        return AgentResult(
            self.name,
            status,
            "CAPA draft generated with decision and RCA context",
            {"capa": capa, "requiresReview": not is_valid},
            warnings,
        )

