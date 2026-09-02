"""Optional LangGraph workflow skeleton for CAPA/RCA orchestration.

The production orchestrator remains the source of truth. This module wraps
the same agents in a graph when LangGraph is installed, and falls back to the
existing orchestrator when it is not. That keeps CI and current deployment
stable while giving the LangChain branch a concrete place to add agentic
control flow, MCP tools, and review gates.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional, TypedDict

from config import AGENT_KILL_SWITCH, AGENT_MAX_TURNS
from services.agents.audit import log_agent_event
from services.agents.capa_draft_agent import CAPADraftAgent
from services.agents.decision_agent import DecisionEligibilityAgent
from services.agents.orchestrator import CapaAgentOrchestrator
from services.agents.rca_scoring_agent import RCAScoringAgent
from services.agents.record_intake_agent import RecordIntakeAgent
from services.logging_config import get_logger
from services.mcp_registry import enabled_mcp_tools

log = get_logger(__name__)


class CapaGraphState(TypedDict, total=False):
    record_id: str
    triggered_by: str
    save_draft: bool
    run_id: str
    decision_answers: dict[str, Any] | None
    turns_used: int
    steps: list[dict[str, Any]]
    record: dict[str, Any]
    decision: dict[str, Any]
    rca_score: dict[str, Any]
    draft: dict[str, Any] | None
    saved_capa: dict[str, Any] | None
    mcp_tools: list[dict[str, Any]]
    status: str
    error: str
    recordId: str
    agentRunId: str
    capaTriggered: bool
    requiresHumanApproval: bool


def run_capa_workflow(
    record_id: str,
    *,
    triggered_by: str = "manual",
    save_draft: bool = False,
    parent_run_id: Optional[str] = None,
    decision_answers: Optional[dict] = None,
) -> dict:
    """Run CAPA workflow, using LangGraph when explicitly enabled."""

    if os.getenv("LANGGRAPH_WORKFLOW_ENABLED", "false").lower() != "true":
        return CapaAgentOrchestrator().run(
            record_id,
            triggered_by=triggered_by,
            save_draft=save_draft,
            parent_run_id=parent_run_id,
            decision_answers=decision_answers,
        )

    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        log.warning("langgraph.workflow_unavailable")
        return CapaAgentOrchestrator().run(
            record_id,
            triggered_by=triggered_by,
            save_draft=save_draft,
            parent_run_id=parent_run_id,
            decision_answers=decision_answers,
        )

    if AGENT_KILL_SWITCH:
        return {"status": "error", "error": "Agent kill switch is active.", "recordId": record_id, "steps": []}

    graph = StateGraph(CapaGraphState)
    graph.add_node("intake", _intake_node)
    graph.add_node("eligibility", _eligibility_node)
    graph.add_node("rca", _rca_node)
    graph.add_node("capa_draft", _draft_node)
    graph.add_node("finish", _finish_node)
    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", _abort_or_continue, {"continue": "eligibility", "abort": "finish"})
    graph.add_edge("eligibility", "rca")
    graph.add_conditional_edges("rca", _draft_or_finish, {"draft": "capa_draft", "finish": "finish"})
    graph.add_edge("capa_draft", "finish")
    graph.add_edge("finish", END)

    initial: CapaGraphState = {
        "record_id": record_id,
        "triggered_by": triggered_by,
        "save_draft": save_draft,
        "run_id": parent_run_id or f"RUN-{uuid.uuid4().hex[:12].upper()}",
        "decision_answers": decision_answers,
        "turns_used": 0,
        "steps": [],
        "mcp_tools": enabled_mcp_tools(),
    }
    result = graph.compile().invoke(initial)
    return dict(result)


def run_langgraph_capa_workflow(
    record_id: str,
    *,
    triggered_by: str = "manual",
    save_draft: bool = False,
    parent_run_id: Optional[str] = None,
    decision_answers: Optional[dict] = None,
) -> dict:
    """Backward-compatible alias for the LangGraph branch entry point."""

    return run_capa_workflow(
        record_id,
        triggered_by=triggered_by,
        save_draft=save_draft,
        parent_run_id=parent_run_id,
        decision_answers=decision_answers,
    )


def _next_turn(state: CapaGraphState, step_name: str) -> None:
    turns_used = int(state.get("turns_used", 0)) + 1
    if turns_used > AGENT_MAX_TURNS:
        raise RuntimeError(f"Agent turn budget exceeded ({AGENT_MAX_TURNS}); aborting at {step_name}")
    state["turns_used"] = turns_used


def _append_step(state: CapaGraphState, result: Any, event: str) -> None:
    payload = result.to_dict()
    state.setdefault("steps", []).append(payload)
    log_agent_event(
        result.agent,
        event,
        result.status,
        run_id=state["run_id"],
        record_id=state["record_id"],
        triggered_by=state.get("triggered_by", "manual"),
        details={"summary": result.summary, "warnings": result.warnings},
    )


def _intake_node(state: CapaGraphState) -> CapaGraphState:
    _next_turn(state, "record_intake")
    result = RecordIntakeAgent().run(state["record_id"])
    _append_step(state, result, "record_intake")
    if result.status == "error":
        state["status"] = "error"
        state["error"] = result.summary
        return state
    state["record"] = result.data["record"]
    return state


def _eligibility_node(state: CapaGraphState) -> CapaGraphState:
    _next_turn(state, "eligibility_decision")
    result = DecisionEligibilityAgent().run(
        state["record"],
        explicit_answers=state.get("decision_answers"),
    )
    _append_step(state, result, "eligibility_decision")
    state["decision"] = result.data["decision"]
    return state


def _rca_node(state: CapaGraphState) -> CapaGraphState:
    _next_turn(state, "rca_scoring")
    result = RCAScoringAgent().run(state["record"])
    _append_step(state, result, "rca_scoring")
    state["rca_score"] = result.data["score"]
    return state


def _draft_node(state: CapaGraphState) -> CapaGraphState:
    _next_turn(state, "capa_draft")
    result = CAPADraftAgent().run(state["record"], state["decision"], state["rca_score"])
    _append_step(state, result, "capa_draft")
    state["draft"] = result.data["capa"]
    if state.get("save_draft"):
        state["saved_capa"] = CapaAgentOrchestrator._save_draft(
            state["record"],
            result.data["capa"],
            state.get("triggered_by", "manual"),
        )
    return state


def _finish_node(state: CapaGraphState) -> CapaGraphState:
    if state.get("status") == "error":
        return state
    state["status"] = "ok"
    state["recordId"] = state["record_id"]
    state["agentRunId"] = state["run_id"]
    state["capaTriggered"] = bool(state.get("decision", {}).get("capa_triggered"))
    state["requiresHumanApproval"] = True
    return state


def _abort_or_continue(state: CapaGraphState) -> str:
    return "abort" if state.get("status") == "error" else "continue"


def _draft_or_finish(state: CapaGraphState) -> str:
    return "draft" if state.get("decision", {}).get("capa_triggered") else "finish"
