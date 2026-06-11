# routes/decision.py
# Handles: GET  /decision-tree              → decision tree page
#          GET  /api/decision/gates/<type>  → gate definitions
#          POST /api/decision/evaluate      → gate evaluation

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from data.gate_definitions import GATE_DEFS
from services.rca_service  import evaluate_gates

decision_bp = Blueprint("decision", __name__)


# ── Page route ────────────────────────────────────────────
@decision_bp.route("/decision-tree")
@login_required
def page_decision_tree():
    return render_template("decision_tree/index.html")


# ── API routes ────────────────────────────────────────────
@decision_bp.route("/api/decision/gates/<source_type>", methods=["GET"])
@login_required
def api_get_gates(source_type):
    """
    Returns the gate definitions for the given source type.
    Used by the frontend to build the decision form dynamically.
    source_type: complaint | deviation | cc
    """
    gates = GATE_DEFS.get(source_type)
    if gates is None:
        return jsonify({
            "error": f"Unknown source type: '{source_type}'. "
                     f"Use: complaint | deviation | cc"
        }), 400
    return jsonify({"source": source_type, "gates": gates})


@decision_bp.route("/api/decision/evaluate", methods=["POST"])
@login_required
def api_evaluate():
    """
    Evaluates all gates server-side using Python logic.
    Body: { source: 'complaint', answers: { gate_id: true/false } }
    Returns triggered gate, recommendation, regulatory refs.
    """
    body    = request.get_json(force=True) or {}
    source  = body.get("source", "")
    answers = body.get("answers", {})

    if not source:
        return jsonify({"error": "Missing 'source' in request body"}), 400

    if source not in GATE_DEFS:
        return jsonify({
            "error": f"Unknown source: '{source}'. "
                     f"Use: complaint | deviation | cc"
        }), 400

    try:
        return jsonify(evaluate_gates(source, answers))
    except Exception as e:
        return jsonify({"error": str(e)}), 502