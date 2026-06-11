# routes/dashboard.py
# GET /              → dashboard page
# GET /api/records   → role-filtered records JSON
# GET /api/records/<id> → single record (all roles, ID lookup)
# GET /api/metrics   → role-scoped KPI counts
# GET /api/analytics → chart data (all roles)
# GET /api/health    → server status

from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from config import MOCK_MODE, AI_MODEL
from data.records import (
    get_all_records, get_records_by_owner,
    update_record_status, get_all_capas, get_capas_by_owner,
)
from services.analytics_service import (
    priority_distribution, status_pipeline, type_breakdown,
)

dashboard_bp = Blueprint("dashboard", __name__)


# ── Page ──────────────────────────────────────────────────
@dashboard_bp.route("/")
@login_required
def page_dashboard():
    active_filter = request.args.get("type", "")
    return render_template("dashboard/index.html",
                           active_filter=active_filter)


# ── Records list — role-filtered ──────────────────────────
@dashboard_bp.route("/api/records", methods=["GET"])
@login_required
def api_get_records():
    rtype  = request.args.get("type")
    sector = request.args.get("sector")
    status = request.args.get("status")
    limit  = int(request.args.get("limit", 200000))

    # admin/quality see all; user sees only their own
    if current_user.sees_all_records():
        recs = get_all_records()
    else:
        recs = get_records_by_owner(current_user.username)

    if rtype:  recs = [r for r in recs if r.get("type")   == rtype]
    if sector: recs = [r for r in recs if r.get("sector") == sector]
    if status: recs = [r for r in recs if r.get("status") == status]

    return jsonify({"records": recs[:limit], "total": len(recs)})


# ── Single record — ID lookup for all roles ───────────────
@dashboard_bp.route("/api/records/<record_id>", methods=["GET"])
@login_required
def api_get_record(record_id):
    recs = get_all_records()
    rec  = next((r for r in recs if r["id"] == record_id), None)
    if not rec:
        return jsonify({"error": f"Record {record_id} not found"}), 404
    return jsonify(rec)


@dashboard_bp.route("/api/records/<record_id>/status", methods=["PATCH"])
@login_required
def api_update_status(record_id):
    body = request.get_json(force=True) or {}
    rec  = update_record_status(record_id, body.get("status", ""))
    if not rec:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"id": record_id, "status": rec["status"]})


# ── Metrics — role-scoped ─────────────────────────────────
@dashboard_bp.route("/api/metrics", methods=["GET"])
@login_required
def api_metrics():
    if current_user.sees_all_records():
        recs  = get_all_records()
        capas = get_all_capas()
    else:
        recs  = get_records_by_owner(current_user.username)
        capas = get_capas_by_owner(current_user.username)

    return jsonify({
        "total":          len(recs),
        "eligible":       sum(1 for r in recs if r.get("status") == "Draft Generated"),
        "under_review":   sum(1 for r in recs if r.get("status") == "Under Review"),
        "approved":       sum(1 for r in recs if r.get("status") == "Approved"),
        "critical":       sum(1 for r in recs if r.get("priority") == "Critical"),
        "medical_device": sum(1 for r in recs if r.get("sector")  == "Medical Device"),
        "biopharma":      sum(1 for r in recs if r.get("sector")  == "BioPharma"),
        "change_ctrl":    sum(1 for r in recs if r.get("type")    == "cc"),
        "capa_drafts":    len(capas),
        "role":           current_user.role,
        "sees_all":       current_user.sees_all_records(),
    })


# ── Analytics — open to all logged-in users ───────────────
@dashboard_bp.route("/api/analytics", methods=["GET"])
@login_required
def api_analytics():
    try:
        from collections import Counter
        capas  = get_all_capas()
        counts = Counter(c.get("status", "Unknown") for c in capas)
        prio   = priority_distribution()
        stat   = status_pipeline()
        typ    = type_breakdown()

        if "total" not in prio:
            prio["total"] = len(get_all_records())

        return jsonify({
            "priority": prio,
            "status":   stat,
            "type":     typ,
            "capa_status": {
                "labels": ["Under Review", "Approved", "Rejected", "Closed"],
                "values": [
                    counts.get("Under Review", 0),
                    counts.get("Approved",     0),
                    counts.get("Rejected",     0),
                    counts.get("Closed",       0),
                ],
                "colors": ["#f59e0b", "#10b981", "#ef4444", "#6366f1"],
                "total":  len(capas),
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Health ────────────────────────────────────────────────
@dashboard_bp.route("/api/health", methods=["GET"])
@login_required
def api_health():
    return jsonify({
        "status":    "ok",
        "framework": "Flask",
        "mock_mode": MOCK_MODE,
        "ai_model":  AI_MODEL,
        "records":   len(get_all_records()),
        "timestamp": datetime.now().isoformat(),
    })