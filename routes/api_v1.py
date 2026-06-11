# routes/api_v1.py
# ══════════════════════════════════════════════════════════════
# QMS GenAI — REST API v1
# Versioned, API-key authenticated, CORS-enabled
# Used by: Salesforce LWC, external integrations, mobile apps
#
# Authentication: X-API-Key header
# Set API_KEY in .env — share with Salesforce Named Credential
#
# Endpoints:
#   GET  /api/v1/health
#   GET  /api/v1/records            — paginated record list
#   GET  /api/v1/records/<id>       — single record
#   POST /api/v1/capa/generate      — generate CAPA draft
#   POST /api/v1/capa/save          — save CAPA
#   GET  /api/v1/capas              — list CAPAs
#   GET  /api/v1/capas/<id>         — single CAPA
#   PATCH /api/v1/capas/<id>/status — approve / reject
#   POST /api/v1/rca/analyze        — run RCA
#   GET  /api/v1/analytics          — chart data
#   POST /api/v1/webhooks/salesforce — receive SF events
# ══════════════════════════════════════════════════════════════

import os
import hmac
import hashlib
import json
from datetime import datetime
from functools import wraps
from flask import Blueprint, jsonify, request, g

from data.records import (
    get_all_records, get_record_by_id,
    get_all_capas, get_capa_by_id,
    save_capa, update_capa_status,
)
from services.ai_service   import generate_capa_draft
from services.rca_service  import build_five_why, build_fishbone

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# ── Config ────────────────────────────────────────────────────
API_KEY      = os.getenv("API_V1_KEY", "")        # set in .env
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://*.salesforce.com,https://*.force.com,http://localhost:5000"
).split(",")


# ── CORS helper ───────────────────────────────────────────────
def _add_cors(response):
    origin = request.headers.get("Origin", "")
    for pattern in ALLOWED_ORIGINS:
        p = pattern.strip().replace("*.", "")
        if p in origin or origin == pattern.strip():
            response.headers["Access-Control-Allow-Origin"]  = origin
            response.headers["Access-Control-Allow-Headers"] = \
                "Content-Type, X-API-Key, Authorization"
            response.headers["Access-Control-Allow-Methods"] = \
                "GET, POST, PATCH, OPTIONS"
            break
    return response


@api_v1_bp.after_request
def after_request(response):
    return _add_cors(response)


@api_v1_bp.route("/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    resp = jsonify({"status": "ok"})
    return _add_cors(resp)


# ── Authentication decorator ──────────────────────────────────
def require_api_key(fn):
    """
    Checks X-API-Key header or ?api_key= query param.
    If API_V1_KEY is not set in .env, accepts all requests
    (for local dev / demo mode).
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not API_KEY:
            # Dev mode — no key required
            return fn(*args, **kwargs)
        provided = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
            or ""
        )
        if not hmac.compare_digest(provided, API_KEY):
            return jsonify({
                "error": "Unauthorized",
                "message": "Valid X-API-Key header required",
            }), 401
        return fn(*args, **kwargs)
    return wrapper


# ── Standard response wrapper ─────────────────────────────────
def _ok(data, status=200):
    return jsonify({
        "status":    "success",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data":      data,
    }), status


def _err(message, status=400, code=None):
    return jsonify({
        "status":  "error",
        "error":   code or "bad_request",
        "message": message,
    }), status


# ══════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/health", methods=["GET"])
def health():
    return _ok({
        "service":   "QMS GenAI",
        "version":   "1.0",
        "status":    "healthy",
        "records":   len(get_all_records()),
        "capas":     len(get_all_capas()),
        "mock_mode": os.getenv("MOCK_MODE", "true"),
    })


# ══════════════════════════════════════════════════════════════
# RECORDS
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/records", methods=["GET"])
@require_api_key
def list_records():
    """
    Paginated record list.
    Query params: page, per_page, type, sector, priority, status, q (search)
    """
    page     = max(1, int(request.args.get("page",     1)))
    per_page = min(100, int(request.args.get("per_page", 25)))
    rtype    = request.args.get("type")
    sector   = request.args.get("sector")
    priority = request.args.get("priority")
    status   = request.args.get("status")
    q        = (request.args.get("q") or "").lower().strip()

    recs = get_all_records()

    # Filter
    if rtype:    recs = [r for r in recs if r.get("type")     == rtype]
    if sector:   recs = [r for r in recs if r.get("sector")   == sector]
    if priority: recs = [r for r in recs if r.get("priority") == priority]
    if status:   recs = [r for r in recs if r.get("status")   == status]
    if q:        recs = [r for r in recs if q in r.get("id","").lower()
                         or q in r.get("title","").lower()
                         or q in r.get("description","").lower()]

    total   = len(recs)
    start   = (page - 1) * per_page
    page_recs = recs[start : start + per_page]

    return _ok({
        "records":    page_recs,
        "total":      total,
        "page":       page,
        "per_page":   per_page,
        "pages":      (total + per_page - 1) // per_page,
        "has_next":   start + per_page < total,
        "has_prev":   page > 1,
    })


@api_v1_bp.route("/records/<record_id>", methods=["GET"])
@require_api_key
def get_record(record_id):
    rec = get_record_by_id(record_id)
    if not rec:
        return _err(f"Record {record_id} not found", 404, "not_found")
    return _ok(rec)


# ══════════════════════════════════════════════════════════════
# CAPA
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/capa/generate", methods=["POST"])
@require_api_key
def api_generate_capa():
    """
    Generate a CAPA draft for a record.
    Body: { "record_id": "CMP-2024-0891" }
       or { "record": { full record object } }
    """
    body = request.get_json(force=True) or {}

    record = body.get("record")
    if not record:
        rid = body.get("record_id") or body.get("recordId")
        if not rid:
            return _err("Provide record_id or record object", 400)
        record = get_record_by_id(rid)
        if not record:
            return _err(f"Record {rid} not found", 404, "not_found")

    try:
        capa = generate_capa_draft(record)
        return _ok({
            "capa":           capa,
            "source_record":  record.get("id"),
            "generated_at":   datetime.utcnow().isoformat() + "Z",
        }, 201)
    except Exception as e:
        return _err(f"CAPA generation failed: {str(e)}", 500, "generation_error")


@api_v1_bp.route("/capa/save", methods=["POST"])
@require_api_key
def api_save_capa():
    """
    Save a CAPA draft.
    Body: full CAPA payload (sourceRecordId, rootCause, etc.)
    """
    body = request.get_json(force=True) or {}
    if not body.get("sourceRecordId"):
        return _err("sourceRecordId is required", 400)

    import uuid
    capa_id = f"CAPA-{datetime.now().year}-{str(uuid.uuid4())[:8].upper()}"
    capa_record = {
        "capaId":             capa_id,
        "sourceRecordId":     body.get("sourceRecordId"),
        "sourceRecordType":   body.get("sourceRecordType", ""),
        "sourceRecordTitle":  body.get("sourceRecordTitle", ""),
        "sector":             body.get("sector", ""),
        "priority":           body.get("priority", "Medium"),
        "site":               body.get("site", ""),
        "status":             "Under Review",
        "rootCause":          body.get("rootCause", ""),
        "immediateAction":    body.get("immediateAction", ""),
        "correctiveAction":   body.get("correctiveAction", ""),
        "preventiveAction":   body.get("preventiveAction", ""),
        "capaOwner":          body.get("capaOwner", ""),
        "effectivenessCheck": body.get("effectivenessCheck", ""),
        "riskRating":         body.get("riskRating", "Medium"),
        "regulatoryRef":      body.get("regulatoryRef", []),
        "estimatedClosureDays": body.get("estimatedClosureDays", 30),
        "notes":              body.get("notes", ""),
        "createdBy":          body.get("createdBy", "api"),
        "createdByUsername":  body.get("createdByUsername", "api"),
        "createdByRole":      body.get("createdByRole", "api"),
        "createdAt":          datetime.utcnow().isoformat(),
        "updatedAt":          datetime.utcnow().isoformat(),
        "_source":            "api_v1",
    }
    save_capa(capa_record)
    return _ok({"capaId": capa_id, "status": "Under Review"}, 201)


@api_v1_bp.route("/capas", methods=["GET"])
@require_api_key
def list_capas():
    page     = max(1, int(request.args.get("page",     1)))
    per_page = min(100, int(request.args.get("per_page", 25)))
    status   = request.args.get("status")
    capas    = get_all_capas()
    if status:
        capas = [c for c in capas if c.get("status") == status]
    total    = len(capas)
    start    = (page - 1) * per_page
    return _ok({
        "capas":    capas[start : start + per_page],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
    })


@api_v1_bp.route("/capas/<capa_id>", methods=["GET"])
@require_api_key
def get_capa(capa_id):
    capa = get_capa_by_id(capa_id)
    if not capa:
        return _err(f"CAPA {capa_id} not found", 404, "not_found")
    return _ok(capa)


@api_v1_bp.route("/capas/<capa_id>/status", methods=["PATCH"])
@require_api_key
def update_status(capa_id):
    body   = request.get_json(force=True) or {}
    status = body.get("status")
    valid  = ["Under Review", "Approved", "Rejected", "Closed"]
    if status not in valid:
        return _err(f"status must be one of: {', '.join(valid)}", 400)
    updated = update_capa_status(capa_id, status)
    if not updated:
        return _err(f"CAPA {capa_id} not found", 404, "not_found")
    return _ok({"capaId": capa_id, "status": status})


# ══════════════════════════════════════════════════════════════
# RCA
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/rca/analyze", methods=["POST"])
@require_api_key
def api_rca():
    """
    Run RCA on a record.
    Body: { "record_id": "...", "method": "5why" | "fishbone" }
    """
    body   = request.get_json(force=True) or {}
    method = body.get("method", "fishbone")
    record = body.get("record")

    if not record:
        rid = body.get("record_id") or body.get("recordId")
        if not rid:
            return _err("Provide record_id or record object", 400)
        record = get_record_by_id(rid)
        if not record:
            return _err(f"Record {rid} not found", 404, "not_found")

    try:
        rca = build_five_why(record) if method == "5why" else build_fishbone(record)
        return _ok({"rca": rca, "method": method})
    except Exception as e:
        return _err(str(e), 500, "rca_error")


# ══════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/analytics", methods=["GET"])
@require_api_key
def api_analytics():
    from services.analytics_service import (
        priority_distribution, status_pipeline, type_breakdown
    )
    from collections import Counter
    try:
        capas  = get_all_capas()
        counts = Counter(c.get("status", "Unknown") for c in capas)
        return _ok({
            "priority":    priority_distribution(),
            "status":      status_pipeline(),
            "type":        type_breakdown(),
            "capa_status": {
                "labels": ["Under Review","Approved","Rejected","Closed"],
                "values": [counts.get(s,0) for s in
                           ["Under Review","Approved","Rejected","Closed"]],
                "total":  len(capas),
            },
        })
    except Exception as e:
        return _err(str(e), 500)


# ══════════════════════════════════════════════════════════════
# SALESFORCE WEBHOOK — receives events from Salesforce Platform Events
# ══════════════════════════════════════════════════════════════
@api_v1_bp.route("/webhooks/salesforce", methods=["POST"])
def salesforce_webhook():
    """
    Receives Salesforce Platform Events or Outbound Messages.
    Verifies signature if SF_WEBHOOK_SECRET is set.
    Expected payload: { "event": "case_created"|"case_updated", "caseId": "...", "record": {...} }
    """
    secret = os.getenv("SF_WEBHOOK_SECRET", "")
    if secret:
        sig = request.headers.get("X-Salesforce-Signature", "")
        expected = hmac.new(
            secret.encode(), request.data, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return _err("Invalid signature", 401, "unauthorized")

    body  = request.get_json(force=True) or {}
    event = body.get("event", "unknown")

    if event == "case_created" and body.get("record"):
        # Auto-generate CAPA on new Salesforce case
        try:
            record = body["record"]
            capa   = generate_capa_draft(record)
            return _ok({
                "action":     "capa_generated",
                "capa_draft": capa,
                "case_id":    body.get("caseId"),
            })
        except Exception as e:
            return _err(str(e), 500)

    return _ok({"action": "received", "event": event})
