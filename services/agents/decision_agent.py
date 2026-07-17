from services.agents.base import AgentResult


class DecisionEligibilityAgent:
    name = "decision_eligibility_agent"

    def run(self, record: dict) -> AgentResult:
        from services.rca_service import evaluate_gates

        source = record.get("type") or "deviation"
        if source not in {"complaint", "deviation", "cc"}:
            source = "deviation"
        answers = self._infer_answers(source, record)
        decision = evaluate_gates(source, answers)
        status = "ok" if decision.get("capa_triggered") else "monitor"
        return AgentResult(
            self.name,
            status,
            decision.get("recommendation", "Decision completed"),
            {"source": source, "answers": answers, "decision": decision},
        )

    def _infer_answers(self, source: str, record: dict) -> dict:
        text = " ".join(str(record.get(k, "")) for k in ("title", "description", "priority")).lower()
        priority = record.get("priority", "Medium")
        high_risk = priority in ("Critical", "High")
        common = {
            "priority": priority,
            "priority_critical_high": high_risk,
            "recurring": any(w in text for w in ("repeat", "recurring", "trend", "multiple")),
        }
        if source == "complaint":
            return {
                **common,
                "adverse_event": any(w in text for w in ("patient", "injury", "harm", "adverse")),
                "regulatory_reportable": any(w in text for w in ("mdr", "reportable", "recall")),
                "systemic_root_cause": any(w in text for w in ("system", "process", "sop", "trend")),
                "qa_recommendation": high_risk,
            }
        if source == "cc":
            return {
                **common,
                "safety_reg_impact": any(w in text for w in ("safety", "regulatory", "submission")),
                "vv_failure": any(w in text for w in ("validation", "verification", "failed", "failure")),
                "unauthorized_change": any(w in text for w in ("unauthorized", "without approval")),
                "cqa_affected": any(w in text for w in ("cqa", "critical quality", "parameter")),
                "supplier_failure": any(w in text for w in ("supplier", "cmo", "site transfer")),
                "repeat_failure": common["recurring"],
            }
        return {
            **common,
            "batch_patient_impact": any(w in text for w in ("batch", "patient", "released")),
            "cqa_breach": any(w in text for w in ("cqa", "ccp", "out of spec", "oos")),
            "validated_process": any(w in text for w in ("validated", "steril", "cleanroom")),
            "equipment_failure": any(w in text for w in ("equipment", "utility", "hvac", "calibration")),
            "gxp_gap": any(w in text for w in ("gxp", "gmp", "data integrity", "documentation")),
        }

