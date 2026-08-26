from services.agents.base import AgentResult


class RCAScoringAgent:
    name = "rca_scoring_agent"

    def run(self, record: dict) -> AgentResult:
        from services.rca_service import assess_five_why, build_five_why

        rca = build_five_why(record)
        score = assess_five_why(rca)
        return AgentResult(
            self.name,
            "ok" if score.get("ready_to_submit") else "warning",
            score.get("verdict_msg", "RCA scored"),
            {"rca": rca, "score": score},
            [] if score.get("ready_to_submit") else ["RCA needs improvement before final approval"],
        )

