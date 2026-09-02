# routes/rca.py
# Handles: GET  /rca/analyze         → RCA analysis page
#          POST /api/rca/five-why    → 5-Why chain
#          POST /api/rca/fishbone    → Fishbone data
#          POST /api/rca/assess      → Accuracy assessment
#          POST /api/rca/propose     → 3 AI-proposed model variants

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from config import RATE_LIMIT_LLM
from services.ai_service  import generate_rca, propose_rca_models
from services.logging_config import get_logger
from services.rca_service import (
    assess_five_why, assess_fishbone,
)

log = get_logger(__name__)
rca_bp = Blueprint("rca", __name__)


@rca_bp.record_once
def _attach_llm_rate_limit(setup_state):
    """Apply per-user LLM cost cap to every RCA route."""
    limiter = setup_state.app.extensions.get("qms_limiter") if setup_state.app else None
    if limiter:
        try:
            limiter.limit(RATE_LIMIT_LLM)(rca_bp)
        except Exception:
            log.exception("rca.rate_limit_attach_failed")


@rca_bp.route("/rca/analyze")
@login_required
def page_rca():
    return render_template("rca/analyze.html",
                           record_id=request.args.get("id", ""))


@rca_bp.route("/api/rca/fishbone", methods=["POST"])
@login_required
def api_fishbone():
    body   = request.get_json(silent=True) or {}
    record = body.get("record", {})
    if not record:
        return jsonify({"error": "Missing 'record'"}), 400
    try:
        return jsonify(generate_rca(record, method="fishbone"))
    except Exception:
        # Never return 502 — always give the user something to work with
        from services.rca_service import build_fishbone
        result = build_fishbone(record)
        result["_fallback"] = True
        return jsonify(result), 200


@rca_bp.route("/api/rca/five-why", methods=["POST"])
@login_required
def api_five_why():
    body   = request.get_json(silent=True) or {}
    record = body.get("record", {})
    if not record:
        return jsonify({"error": "Missing 'record'"}), 400
    try:
        return jsonify(generate_rca(record, method="5why"))
    except Exception:
        from services.rca_service import build_five_why
        result = build_five_why(record)
        result["_fallback"] = True
        return jsonify(result), 200

@rca_bp.route("/api/rca/assess", methods=["POST"])
@login_required
def api_assess():
    """
    Scores RCA on Specificity, Actionability, Completeness.
    Returns per-step scores + overall verdict + AI improvement suggestions.
    If overall_score < 55, needs_ai_help = True is returned.
    """
    body     = request.get_json(silent=True) or {}
    method   = body.get("method", "5why")
    rca_data = body.get("rca_data", {})
    if not rca_data:
        return jsonify({"error": "Missing 'rca_data'"}), 400
    try:
        if method == "fishbone":
            return jsonify(assess_fishbone(rca_data))
        return jsonify(assess_five_why(rca_data))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@rca_bp.route("/api/rca/propose", methods=["POST"])
@login_required
def api_propose():
    """
    Generates 3 AI-proposed RCA models at Basic / Standard / Enhanced
    quality levels (~60% / ~75% / ~80% accuracy scores).
    Called when: user clicks 'AI Improve' OR score < 55%.
    Body: { record: {...}, method: '5why' | 'fishbone' }
    """
    body   = request.get_json(silent=True) or {}
    record = body.get("record", {})
    method = body.get("method", "fishbone")
    if not record:
        return jsonify({"error": "Missing 'record'"}), 400
    try:
        return jsonify(propose_rca_models(record, method))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
