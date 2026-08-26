# routes/analytics.py
from flask import request, current_app
from collections import Counter
from flask import Blueprint, jsonify, render_template
from flask_login import login_required, current_user
from services.analytics_service import (
    priority_distribution, status_pipeline, type_breakdown,
)
from services.logging_config import get_logger
from data.records import get_all_capas, get_all_records, get_record_by_id, get_capa_by_id

log = get_logger(__name__)
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
    except Exception:
        # str(e) previously leaked DB errors and internal service names to the
        # client. Full traceback stays server-side; client gets a generic message.
        log.exception("analytics.failed")
        return jsonify({"error": "Analytics generation failed."}), 500


from services.audit_service import get_recent_activity, get_audit_trail

@analytics_bp.route("/audit-trail")
@login_required
def page_audit():
    return render_template("analytics/audit.html")


def _user_owns_record(record_id: str) -> bool:
    if current_user.sees_all_records():
        return True
    rec = get_record_by_id(record_id)
    return bool(rec and (rec.get("owner") or "") == current_user.username)


def _user_owns_capa(capa_id: str) -> bool:
    if current_user.sees_all_records():
        return True
    capa = get_capa_by_id(capa_id)
    if not capa:
        return False
    owner = (capa.get("createdByUsername") or "").strip()
    return owner == current_user.username


@analytics_bp.route("/api/audit", methods=["GET"])
@login_required
def api_audit():
    """Audit trail is regulated content. Regular users can only inspect the
    trail for records/CAPAs they own; admin/quality see the full stream."""
    record_id = request.args.get("record")
    capa_id   = request.args.get("capa")
    try:
        limit = max(1, min(500, int(request.args.get("limit", 50))))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid limit"}), 400

    if record_id:
        if not _user_owns_record(record_id):
            return jsonify({"error": "Not authorised"}), 403
        entries = get_audit_trail(record_id=record_id, limit=limit)
    elif capa_id:
        if not _user_owns_capa(capa_id):
            return jsonify({"error": "Not authorised"}), 403
        entries = get_audit_trail(capa_id=capa_id, limit=limit)
    else:
        if not current_user.sees_all_records():
            return jsonify({"error": "Global audit access requires quality/admin role"}), 403
        entries = get_recent_activity(limit=limit)
    return jsonify({"entries": entries, "total": len(entries)})
