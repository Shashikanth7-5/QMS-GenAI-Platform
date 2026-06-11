# routes/analytics.py
from flask import request
from collections import Counter
from flask import Blueprint, jsonify, render_template
from flask_login import login_required
from services.analytics_service import (
    priority_distribution, status_pipeline, type_breakdown,
)
from data.records import get_all_capas, get_all_records

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@login_required
def page_analytics():
    return render_template("analytics/index.html")


@analytics_bp.route("/api/analytics", methods=["GET"])
@login_required
def api_analytics():
    try:
        capas  = get_all_capas()
        counts = Counter(c.get("status", "Unknown") for c in capas)

        prio = priority_distribution()
        stat = status_pipeline()
        typ  = type_breakdown()

        if "total" not in prio:
            prio["total"] = len(get_all_records())

        capa_status = {
            "labels": ["Under Review", "Approved", "Rejected", "Closed"],
            "values": [
                counts.get("Under Review", 0),
                counts.get("Approved",     0),
                counts.get("Rejected",     0),
                counts.get("Closed",       0),
            ],
            "colors": ["#f59e0b", "#10b981", "#ef4444", "#6366f1"],
            "total":  len(capas),
        }

        return jsonify({
            "priority":    prio,
            "status":      stat,
            "type":        typ,
            "capa_status": capa_status,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
from services.audit_service import get_recent_activity, get_audit_trail

@analytics_bp.route("/audit-trail")
@login_required
def page_audit():
    return render_template("analytics/audit.html")

@analytics_bp.route("/api/audit", methods=["GET"])
@login_required
def api_audit():
    record_id = request.args.get("record")
    capa_id   = request.args.get("capa")
    limit     = int(request.args.get("limit", 50))
    if record_id:
        entries = get_audit_trail(record_id=record_id, limit=limit)
    elif capa_id:
        entries = get_audit_trail(capa_id=capa_id, limit=limit)
    else:
        entries = get_recent_activity(limit=limit)
    return jsonify({"entries": entries, "total": len(entries)})