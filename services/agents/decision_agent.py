"""Eligibility-decision agent.

Regulated CAPA gates must be answered by a human or a validated
classifier — not by naive substring matching against free-text
record descriptions. This agent:

  * Requires explicit answers when ``require_explicit_answers=True``.
  * Otherwise treats substring inference as a low-confidence HINT and
    emits warnings for every gate that was inferred rather than
    explicitly provided.

The old fully-inferred behaviour is retained under the ``inferred``
key of the returned decision so audit callers can see exactly which
answers were guessed.
"""

from __future__ import annotations

import os
from typing import Optional

from services.agents.base import AgentResult

_REQUIRE_EXPLICIT = os.getenv("AGENT_DECISION_REQUIRE_EXPLICIT", "false").lower() == "true"


class DecisionEligibilityAgent:
    name = "decision_eligibility_agent"

    def run(
        self,
        record: dict,
        *,
        explicit_answers: Optional[dict] = None,
        require_explicit: Optional[bool] = None,
    ) -> AgentResult:
        from services.rca_service import evaluate_gates

        from services.workflow_config import decision_source_for

        source = decision_source_for(record.get("type") or "deviation")

        inferred = self._infer_answers(source, record)
        answers = dict(inferred)
        inferred_keys = set(inferred.keys())

        if explicit_answers:
            for key, value in explicit_answers.items():
                if key in inferred:
                    inferred_keys.discard(key)
                answers[key] = value

        must_be_explicit = _REQUIRE_EXPLICIT if require_explicit is None else require_explicit
        warnings: list[str] = []
        # Any gate still using an inferred answer is flagged so reviewers see it.
        # Boolean gates are the risky ones — priority/priority_critical_high come from
        # structured record fields and are safe to derive.
        safe_inferred = {"priority", "priority_critical_high"}
        unsafe_inferred = sorted(inferred_keys - safe_inferred)
        if unsafe_inferred:
            hint = ", ".join(unsafe_inferred)
            warnings.append(
                f"Gate answers inferred from free text (not explicitly provided): {hint}. "
                "Confirm with the record owner before approving the CAPA."
            )
            if must_be_explicit:
                return AgentResult(
                    self.name,
                    "error",
                    "Eligibility gates require explicit answers in production.",
                    {"source": source, "answers": answers, "inferredKeys": unsafe_inferred},
                    warnings,
                )

        decision = evaluate_gates(source, answers)
        status = "ok" if decision.get("capa_triggered") else "monitor"
        if warnings:
            status = "warning"
        return AgentResult(
            self.name,
            status,
            decision.get("recommendation", "Decision completed"),
            {
                "source": source,
                "answers": answers,
                "inferredKeys": sorted(unsafe_inferred),
                "decision": decision,
            },
            warnings,
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
