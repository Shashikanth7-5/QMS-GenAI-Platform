"""Agent HTTP surface.

All endpoints require an authenticated user. Anything that operates
against a specific record (intake, decision, RCA, orchestrator run)
additionally verifies the caller is authorised to see that record.
Anything that scans across records (supervisor, access review, audit
export, dead-letter queue) is admin-only.
"""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from config import RATE_LIMIT_AGENTS
from data.records import get_record_by_id
from services.agents.audit import get_agent_events
from services.agents.decision_agent import DecisionEligibilityAgent
from services.agents.orchestrator import CapaAgentOrchestrator, run_access_review
from services.agents.rca_scoring_agent import RCAScoringAgent
from services.agents.record_intake_agent import RecordIntakeAgent
from services.agents.supervisor import (AgentSupervisor, get_dead_letters,
                                        get_supervisor_status,
                                        requeue_dead_letter)
from services.logging_config import get_logger

log = get_logger(__name__)

agents_bp = Blueprint("agents", __name__)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def _may_access_record(record: dict) -> bool:
    if not record:
        return False
    if current_user.sees_all_records():
        return True
    return record.get("createdBy") == current_user.username


def _resolve_record(body: dict):
    """Return (record_dict, error_response_or_None). Enforces per-user authz."""
    record = body.get("record")
    if not record:
        rid = body.get("recordId") or body.get("record_id")
        if not rid:
            return None, (jsonify({"error": "Missing record or recordId"}), 400)
        record = get_record_by_id(rid)
        if not record:
            return None, (jsonify({"error": f"Record {rid} not found"}), 404)
    if not _may_access_record(record):
        log.warning(
            "agent.authz.denied",
            extra={"username": current_user.username, "record_id": record.get("id")},
        )
        return None, (jsonify({"error": "Not authorised for this record"}), 403)
    return record, None


@agents_bp.record_once
def _on_registered(setup_state):
    limiter = setup_state.app.extensions.get("qms_limiter") if setup_state.app else None
    if limiter:
        try:
            limiter.limit(RATE_LIMIT_AGENTS)(agents_bp)
        except Exception:
            log.exception("agent.rate_limit_attach_failed")


@agents_bp.route("/admin/agents")
@admin_required
def page_agent_control_center():
    return render_template("agents/control_center.html", active_tab="agents")


@agents_bp.route("/api/agents/record/intake", methods=["POST"])
@login_required
def api_record_intake():
    body = request.get_json(silent=True) or {}
    record_id = body.get("recordId", "")
    if not record_id:
        return jsonify({"error": "Missing recordId"}), 400
    record = get_record_by_id(record_id)
    if record and not _may_access_record(record):
        return jsonify({"error": "Not authorised for this record"}), 403
    result = RecordIntakeAgent().run(record_id)
    status_code = 404 if result.status == "error" else 200
    return jsonify(result.to_dict()), status_code


@agents_bp.route("/api/agents/decision/check", methods=["POST"])
@login_required
def api_decision_check():
    body = request.get_json(silent=True) or {}
    record, err = _resolve_record(body)
    if err:
        return err
    return jsonify(
        DecisionEligibilityAgent()
        .run(record, explicit_answers=body.get("answers"))
        .to_dict()
    )


@agents_bp.route("/api/agents/rca/score", methods=["POST"])
@login_required
def api_rca_score():
    body = request.get_json(silent=True) or {}
    record, err = _resolve_record(body)
    if err:
        return err
    return jsonify(RCAScoringAgent().run(record).to_dict())


@agents_bp.route("/api/agents/capa/run", methods=["POST"])
@login_required
def api_capa_agents_run():
    body = request.get_json(silent=True) or {}
    record_id = body.get("recordId", "")
    if not record_id:
        return jsonify({"error": "Missing recordId"}), 400

    record = get_record_by_id(record_id)
    if not record:
        return jsonify({"error": f"Record {record_id} not found"}), 404
    if not _may_access_record(record):
        return jsonify({"error": "Not authorised for this record"}), 403

    save_draft = bool(body.get("saveDraft", False))
    if save_draft and not current_user.can_create_capa():
        return jsonify({"error": "Quality or Admin access required to save drafts"}), 403

    result = CapaAgentOrchestrator().run(
        record_id,
        triggered_by=current_user.username,
        save_draft=save_draft,
        decision_answers=body.get("answers"),
    )
    return jsonify(result), 404 if result.get("status") == "error" and result.get("recordId") is None else 200


@agents_bp.route("/api/agents/admin/access-review", methods=["POST"])
@admin_required
def api_admin_access_review():
    return jsonify(run_access_review())


@agents_bp.route("/api/agents/supervisor/run", methods=["POST"])
@admin_required
def api_supervisor_run():
    body = request.get_json(silent=True) or {}
    result = AgentSupervisor().run_once(
        triggered_by=current_user.username,
        limit=body.get("limit", 50),
        allow_weekend=bool(body.get("allowWeekend", False)),
    )
    return jsonify(result)


@agents_bp.route("/api/agents/supervisor/dead-letter", methods=["GET"])
@admin_required
def api_supervisor_dead_letter():
    return jsonify({"deadLetters": get_dead_letters()})


@agents_bp.route("/api/agents/supervisor/dead-letter/<record_id>/requeue", methods=["POST"])
@admin_required
def api_supervisor_requeue(record_id: str):
    requeued = requeue_dead_letter(record_id)
    return jsonify({"recordId": record_id, "requeued": requeued}), (200 if requeued else 404)


@agents_bp.route("/api/agents/status", methods=["GET"])
@admin_required
def api_agent_status():
    return jsonify(get_supervisor_status())


@agents_bp.route("/api/agents/audit", methods=["GET"])
@admin_required
def api_agent_audit():
    return jsonify({"events": get_agent_events(
        limit=request.args.get("limit", 100, type=int),
        status=request.args.get("status"),
        agent=request.args.get("agent"),
        record_id=request.args.get("recordId"),
    )})
