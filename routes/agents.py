from functools import wraps

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from services.agents.decision_agent import DecisionEligibilityAgent
from services.agents.orchestrator import CapaAgentOrchestrator, run_access_review
from services.agents.rca_scoring_agent import RCAScoringAgent
from services.agents.record_intake_agent import RecordIntakeAgent

agents_bp = Blueprint("agents", __name__)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


@agents_bp.route("/api/agents/record/intake", methods=["POST"])
@login_required
def api_record_intake():
    record_id = (request.get_json(force=True) or {}).get("recordId", "")
    if not record_id:
        return jsonify({"error": "Missing recordId"}), 400
    result = RecordIntakeAgent().run(record_id)
    return jsonify(result.to_dict()), 404 if result.status == "error" else 200


@agents_bp.route("/api/agents/decision/check", methods=["POST"])
@login_required
def api_decision_check():
    body = request.get_json(force=True) or {}
    record = body.get("record")
    if not record and body.get("recordId"):
        intake = RecordIntakeAgent().run(body["recordId"])
        if intake.status == "error":
            return jsonify(intake.to_dict()), 404
        record = intake.data["record"]
    if not record:
        return jsonify({"error": "Missing record or recordId"}), 400
    return jsonify(DecisionEligibilityAgent().run(record).to_dict())


@agents_bp.route("/api/agents/rca/score", methods=["POST"])
@login_required
def api_rca_score():
    body = request.get_json(force=True) or {}
    record = body.get("record")
    if not record and body.get("recordId"):
        intake = RecordIntakeAgent().run(body["recordId"])
        if intake.status == "error":
            return jsonify(intake.to_dict()), 404
        record = intake.data["record"]
    if not record:
        return jsonify({"error": "Missing record or recordId"}), 400
    return jsonify(RCAScoringAgent().run(record).to_dict())


@agents_bp.route("/api/agents/capa/run", methods=["POST"])
@login_required
def api_capa_agents_run():
    record_id = (request.get_json(force=True) or {}).get("recordId", "")
    if not record_id:
        return jsonify({"error": "Missing recordId"}), 400
    result = CapaAgentOrchestrator().run(record_id)
    return jsonify(result), 404 if result.get("status") == "error" else 200


@agents_bp.route("/api/agents/admin/access-review", methods=["POST"])
@admin_required
def api_admin_access_review():
    return jsonify(run_access_review())
