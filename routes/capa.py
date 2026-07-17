# routes/capa.py
import random
import os
import httpx
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, jsonify,
                   render_template, request, stream_with_context)
from flask_login import login_required, current_user

from services.ai_service import generate_capa, stream_capa
from services.ingestion_service import process_upload, allowed_file
from services.audit_service import (
    log,
    ACTION_CAPA_SAVED, ACTION_CAPA_STATUS_CHANGE,
    ACTION_CAPA_GENERATED, ACTION_CAPA_BATCH_RUN,
    ACTION_RECORD_UPLOADED,
)
from data.records import (
    get_all_records, get_records_by_owner, get_record_by_id,
    update_record_status, save_capa, get_all_capas, get_capas_by_owner,
    get_capa_by_id, update_capa_status, add_uploaded_record,
)

capa_bp = Blueprint("capa", __name__)

_TYPE_LABEL = {
    "complaint": "Complaint", "deviation": "Deviation",
    "cc": "Change Control",   "nc": "Non-Conformance", "audit": "Audit",
}


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def capa_create_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.can_create_capa():
            return jsonify({"error": "Quality or Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


@capa_bp.route("/capa/create")
@login_required
def page_capa_create():
    record_id = request.args.get("id", "")
    record    = get_record_by_id(record_id) if record_id else None
    return render_template("capa/create.html",
                           record=record, record_id=record_id,
                           can_create=current_user.can_create_capa(),
                           can_approve=current_user.can_approve_capa())


@capa_bp.route("/api/capa/generate", methods=["POST"])
@login_required
def api_generate():
    body   = request.get_json(force=True) or {}
    record = body.get("record", {})
    if not record:
        return jsonify({"error": "Missing 'record'"}), 400
    result = generate_capa(record)
    return jsonify(result)


@capa_bp.route("/api/capa/stream", methods=["POST"])
@login_required
def api_stream():
    body   = request.get_json(force=True) or {}
    record = body.get("record", {})
    if not record:
        return jsonify({"error": "Missing 'record'"}), 400
    if current_user.is_user():
        if record.get("createdBy") != current_user.username:
            return jsonify({"error": "Not authorised"}), 403
    try:
        return Response(
            stream_with_context(stream_capa(record)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@capa_bp.route("/api/capa/run-batch", methods=["POST"])
@admin_required
def api_run_batch():
    all_recs = get_all_records()
    all_capas = get_all_capas()
    capa_ids = {c.get("sourceRecordId") for c in all_capas}
    eligible = [r for r in all_recs
                if r.get("status") == "Draft Generated"
                and r["id"] not in capa_ids]

    processed, errors, queued = [], [], []
    actor = {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
    }
    from services.celery_app import EAGER
    from services.tasks import generate_capa_async

    for rec in eligible:
        try:
            result = generate_capa_async.delay(rec["id"], actor)
            if EAGER:
                payload = result.get()
                if payload.get("status") == "done":
                    processed.append({"id": rec["id"], "capaId": payload.get("capaId")})
                else:
                    errors.append({"id": rec["id"], "error": payload.get("error", "unknown error")})
            else:
                queued.append({"id": rec["id"], "taskId": result.id})
        except Exception as e:
            errors.append({"id": rec["id"], "error": str(e)})

    if queued:
        message = f"Batch queued - {len(queued)} CAPA job(s), {len(errors)} errors"
    else:
        message = f"Batch complete - {len(processed)} CAPAs generated, {len(errors)} errors"

    return jsonify({
        "processed": len(processed),
        "queued": len(queued),
        "errors": len(errors),
        "skipped": 0,
        "details": processed,
        "queuedDetails": queued,
        "errorDetails": errors,
        "message": message,
    })


@capa_bp.route("/api/capa/save", methods=["POST"])
@login_required
def api_save():
    body      = request.get_json(force=True) or {}
    record_id = body.get("sourceRecordId", "")
    if not record_id:
        return jsonify({"error": "Missing 'sourceRecordId'"}), 400
    src_record = get_record_by_id(record_id)
    capa_id    = f"CAPA-{datetime.now().year}-{random.randint(1000,9999)}"
    now        = datetime.now().isoformat()
    reg_refs   = body.get("regulatoryRef", [])
    if isinstance(reg_refs, str):
        reg_refs = [r.strip() for r in reg_refs.split(",") if r.strip()]
    capa_record = {
        "capaId":               capa_id,
        "status":               "Under Review",
        "sourceRecordId":       record_id,
        "sourceRecordType":     _TYPE_LABEL.get(
            src_record.get("type","") if src_record else "", "—"),
        "sourceRecordTitle":    src_record.get("title","—") if src_record else "—",
        "sector":               src_record.get("sector","—") if src_record else "—",
        "priority":             src_record.get("priority","—") if src_record else "—",
        "site":                 src_record.get("site","—") if src_record else "—",
        "rootCause":            body.get("rootCause",""),
        "immediateAction":      body.get("immediateAction",""),
        "correctiveAction":     body.get("correctiveAction",""),
        "preventiveAction":     body.get("preventiveAction",""),
        "capaOwner":            body.get("capaOwner",""),
        "effectivenessCheck":   body.get("effectivenessCheck",""),
        "notes":                body.get("notes",""),
        "riskRating":           body.get("riskRating",
            src_record.get("priority","") if src_record else ""),
        "regulatoryRef":        reg_refs,
        "estimatedClosureDays": int(body.get("estimatedClosureDays", 30)),
        "createdBy":            current_user.full_name,
        "createdByUsername":    current_user.username,
        "createdByRole":        current_user.role,
        "createdAt":            now,
        "updatedAt":            now,
    }
    from services.guardrails import validate_capa
    is_valid, warnings = validate_capa(capa_record)

    save_capa(capa_record)
    # Embed into vector store for RAG (non-blocking — never fails the save)
    try:
        from services.vector_store import embed_capa
        embed_capa(capa_record)
    except Exception as _e:
        print(f"[capa] vector embed skipped: {_e}")
    update_record_status(record_id, "Under Review")
    # Embed into vector store for RAG (non-blocking — never fails the save)
    try:
        from services.vector_store import embed_capa
        embed_capa(capa_record)
    except Exception as _e:
        print(f"[capa] vector embed skipped: {_e}")
    log(ACTION_CAPA_SAVED,
        performed_by=current_user.username,
        performed_by_role=current_user.role,
        record_id=record_id,
        capa_id=capa_id,
        entity_type="capa",
        old_value="Draft Generated",
        new_value="Under Review",
        notes=f"CAPA {capa_id} created from record {record_id}",
        ip_address=request.remote_addr)
    return jsonify({
        "capaId": capa_id,
        "status": "Under Review",
        "sourceRecordId": record_id,
        "createdAt": now,
        "message": f"CAPA {capa_id} saved",
        "warnings": warnings,
        "requires_review": not is_valid,
    })


@capa_bp.route("/api/capas", methods=["GET"])
@login_required
def api_get_capas():
    status = request.args.get("status")
    if current_user.sees_all_records():
        capas = get_all_capas()
    else:
        capas = get_capas_by_owner(current_user.username)
    if status:
        capas = [c for c in capas if c.get("status") == status]
    return jsonify({"capas": capas, "total": len(capas)})


@capa_bp.route("/api/capas/<capa_id>", methods=["GET"])
@login_required
def api_get_capa(capa_id: str):
    capa = get_capa_by_id(capa_id)
    if not capa:
        return jsonify({"error": f"CAPA {capa_id} not found"}), 404
    if current_user.is_user() and capa.get("createdByUsername") != current_user.username:
        return jsonify({"error": "Not authorised"}), 403
    return jsonify(capa)

@capa_bp.route("/api/capa/<capa_id>/export", methods=["GET"])
@login_required
def api_export_capa(capa_id: str):
    """Export a CAPA as a downloadable PDF."""
    from data.records import get_capa_by_id
    capa = get_capa_by_id(capa_id)
    if not capa:
        return jsonify({"error": f"CAPA {capa_id} not found"}), 404

    # Users can only export their own CAPAs
    if current_user.is_user() and capa.get("createdByUsername") != current_user.username:
        return jsonify({"error": "Not authorised"}), 403

    # Optional: attach RAG similar cases if the source record is available
    similar = None
    try:
        from data.records import get_record_by_id
        from services.vector_store import find_similar
        rec = get_record_by_id(capa.get("sourceRecordId", ""))
        if rec:
            similar = find_similar(rec, top_k=3)
    except Exception as _e:
        print(f"[capa] export similar lookup skipped: {_e}")

    from services.pdf_service import build_capa_pdf
    pdf_bytes = build_capa_pdf(capa, similar=similar)

    from flask import Response
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{capa_id}.pdf"',
        },
    )

@capa_bp.route("/api/capas/<capa_id>/status", methods=["PATCH"])
@admin_required
def api_update_capa_status(capa_id: str):
    body       = request.get_json(force=True) or {}
    new_status = body.get("status","")
    allowed    = {"Under Review","Approved","Rejected","Closed"}
    if new_status not in allowed:
        return jsonify({"error": f"Invalid status. Use: {', '.join(allowed)}"}), 400
    existing   = get_capa_by_id(capa_id)
    old_status = existing.get("status","Unknown") if existing else "Unknown"
    capa       = update_capa_status(capa_id, new_status)
    if not capa:
        return jsonify({"error": f"CAPA {capa_id} not found"}), 404
    log(ACTION_CAPA_STATUS_CHANGE,
        performed_by=current_user.username,
        performed_by_role=current_user.role,
        capa_id=capa_id,
        record_id=capa.get("sourceRecordId"),
        entity_type="capa",
        field_name="status",
        old_value=old_status,
        new_value=new_status,
        notes=f"CAPA {capa_id} status changed by {current_user.username}",
        ip_address=request.remote_addr)
    return jsonify({
        "capaId":    capa_id,
        "status":    new_status,
        "updatedAt": capa.get("updatedAt"),
    })


@capa_bp.route("/api/records/upload", methods=["POST"])
@login_required
def api_upload_record():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Empty file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400
    try:
        file_bytes            = file.read()
        record                = process_upload(file_bytes, file.filename)
        record["createdBy"]   = current_user.username
        record["createdByName"] = current_user.full_name
        record["createdByRole"] = current_user.role
        if record.get("_insufficient"):
            return jsonify({
                "success":      False,
                "insufficient": True,
                "reason":       record.get("reason","Document does not contain QMS data."),
                "message":      record.get("reason","Please upload a QMS document."),
            }), 422
        saved = add_uploaded_record(record)
        return jsonify({
            "success": True,
            "record":  saved,
            "message": f"Record {saved['id']} extracted successfully.",
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500


@capa_bp.route("/api/records/inquire", methods=["POST"])
@login_required
def api_inquire():
    body     = request.get_json(force=True) or {}
    record   = body.get("record", {})
    question = body.get("question", "")
    history  = body.get("history", [])
    if not record or not question:
        return jsonify({"error": "Missing record or question"}), 400
    try:
        from services.chains.inquiry_chain import run_inquiry_chain
        answer = run_inquiry_chain(record, question, history)
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"[inquire] error: {e}")
        from services.chains.inquiry_chain import _smart_mock
        return jsonify({"answer": _smart_mock(record, question)})

@capa_bp.route("/api/rag/similar", methods=["POST"])
@login_required
def api_rag_similar():
        """
        Return the top-k most similar past CAPAs for a given record.
        Body: { "record": {...}, "top_k": 3 }
        """
        body = request.get_json(force=True) or {}
        record = body.get("record", {})
        top_k = int(body.get("top_k", 3))
        if not record:
            return jsonify({"error": "Missing 'record'"}), 400
        try:
            from services.vector_store import find_similar, collection_stats
            similar = find_similar(record, top_k=top_k)
            stats = collection_stats()
            return jsonify({
                "similar": similar,
                "count": len(similar),
                "total_embedded": stats.get("embedded_capas", 0),
            })
        except Exception as e:
            print(f"[rag] similar failed: {e}")
            return jsonify({"similar": [], "count": 0, "error": str(e)}), 200
