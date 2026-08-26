# routes/capa.py
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, jsonify, render_template, request,
                   stream_with_context)
from flask_login import current_user, login_required

from auth.users import get_user_by_username
from data.records import (add_uploaded_record, get_all_capas, get_all_records,
                          get_capa_by_id, get_capa_by_record_id,
                          get_record_by_id, get_capas_by_owner, save_capa, update_capa_status,
                          update_record_status)
from services.agents.notifications import send_email_notification
from services.agents.orchestrator import new_capa_id
from services.ai_service import generate_capa, stream_capa
from services.audit_service import (ACTION_CAPA_SAVED,
                                    ACTION_CAPA_STATUS_CHANGE,
                                    log)
from services.ingestion_service import allowed_file, process_upload
from services.logging_config import get_logger
from services.security import capa_content_hash
from services.storage import save_upload

logger = get_logger(__name__)
capa_bp = Blueprint("capa", __name__)

_TYPE_LABEL = {
    "complaint": "Complaint", "deviation": "Deviation",
    "cc": "Change Control",   "nc": "Non-Conformance", "audit": "Audit",
}


def _validate_esign(payload: dict, capa_body: dict | None = None):
    esign = payload.get("eSignature") or {}
    password = esign.get("password", "")
    meaning = esign.get("meaning", "")
    if not password:
        return None, (jsonify({
            "error": "Electronic signature required.",
            "basis": ["21 CFR Part 11 §11.200", "EU Annex 11"],
            "message": "Approval/rejection requires password re-entry as reviewer e-signature.",
        }), 400)
    if not current_user.check_password(password):
        logger.warning("capa.esign.rejected",
                       extra={"user": current_user.username, "capa_id": (capa_body or {}).get("capaId")})
        return None, (jsonify({
            "error": "Electronic signature failed.",
            "basis": ["21 CFR Part 11"],
            "message": "Password did not match the logged-in reviewer.",
        }), 403)
    signature = {
        "signedBy": current_user.username,
        "signedByName": current_user.full_name,
        "signedByRole": current_user.role,
        "meaning": meaning or "CAPA workflow decision",
        "signedAt": datetime.utcnow().isoformat() + "Z",
        "basis": ["21 CFR Part 11 §11.200", "EU Annex 11"],
    }
    if capa_body is not None:
        # Bind the signature to a SHA-256 digest of the CAPA content —
        # any edit to root cause / actions / owner invalidates it.
        signature["capaHash"] = capa_content_hash(capa_body)
    return signature, None


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
    body      = request.get_json(silent=True) or {}
    record_id = body.get("sourceRecordId", "")
    if not record_id:
        return jsonify({"error": "Missing 'sourceRecordId'"}), 400
    src_record = get_record_by_id(record_id)
    capa_id    = body.get("capaId") or new_capa_id()
    now        = datetime.now().isoformat()
    reg_refs   = body.get("regulatoryRef", [])
    if isinstance(reg_refs, str):
        reg_refs = [r.strip() for r in reg_refs.split(",") if r.strip()]
    try:
        closure_days = int(body.get("estimatedClosureDays", 30))
    except (TypeError, ValueError):
        return jsonify({"error": "estimatedClosureDays must be an integer"}), 400
    if closure_days < 1 or closure_days > 365:
        return jsonify({"error": "estimatedClosureDays must be between 1 and 365"}), 400
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
        "capaMetadata":         body.get("capaMetadata", {}),
        "estimatedClosureDays": closure_days,
        "createdBy":            current_user.full_name,
        "createdByUsername":    current_user.username,
        "createdByRole":        current_user.role,
        "createdAt":            now,
        "updatedAt":            now,
    }
    from services.guardrails import validate_capa_detailed
    validation = validate_capa_detailed(capa_record)
    capa_record["capaMetadata"] = {
        **(capa_record.get("capaMetadata") or {}),
        "regulatoryBasis": validation.get("basis", []),
        "validationWarnings": validation.get("warnings", []),
    }
    if not validation["can_save"]:
        return jsonify({
            "error": "CAPA draft is missing required information.",
            "message": "Complete the required fields before submitting for review.",
            "validation": validation,
        }), 400

    save_capa(capa_record)
    update_record_status(record_id, "Under Review")
    # Embed into vector store for RAG (non-blocking — never fails the save)
    try:
        from services.vector_store import embed_capa
        embed_capa(capa_record)
    except Exception:
        logger.warning("capa.vector_embed_skipped", exc_info=True,
                       extra={"capa_id": capa_id, "record_id": record_id})
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
        "warnings": validation.get("warnings", []),
        "basis": validation.get("basis", []),
        "requires_review": bool(validation.get("warnings")),
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


@capa_bp.route("/api/capas/by-record/<record_id>", methods=["GET"])
@login_required
def api_get_capa_by_record(record_id: str):
    capa = get_capa_by_record_id(record_id)
    if not capa:
        return jsonify({"error": f"No CAPA draft found for record {record_id}"}), 404
    if current_user.is_user() and capa.get("createdByUsername") != current_user.username:
        return jsonify({"error": "Not authorised"}), 403
    return jsonify(capa)


@capa_bp.route("/api/capa/attachments/upload", methods=["POST"])
@login_required
def api_upload_capa_attachments():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files provided"}), 400

    saved = []
    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            return jsonify({"error": f"Unsupported file type: {file.filename}"}), 400

        saved.append(save_upload(
            file,
            namespace="capa_attachments",
            uploaded_by=current_user.username,
        ))

    return jsonify({"attachments": saved, "count": len(saved)})

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
    except Exception:
        logger.warning("capa.export_similar_lookup_skipped", exc_info=True,
                       extra={"capa_id": capa_id})

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
    requested_status = body.get("status","")
    comment    = body.get("comment","").strip()
    allowed    = {"Under Review","Pending Correction","Approved","Rejected","Closed"}
    if requested_status not in allowed:
        return jsonify({"error": f"Invalid status. Use: {', '.join(allowed)}"}), 400
    existing   = get_capa_by_id(capa_id)
    old_status = existing.get("status","Unknown") if existing else "Unknown"
    if not existing:
        return jsonify({"error": f"CAPA {capa_id} not found"}), 404
    if requested_status in {"Approved", "Rejected"}:
        esign, esign_error = _validate_esign(body, capa_body=existing)
        if esign_error:
            return esign_error
    else:
        esign = None

    new_status = "Pending Correction" if requested_status == "Rejected" else requested_status
    creator_username = existing.get("createdByUsername", "")
    creator = get_user_by_username(creator_username) if creator_username else None
    creator_email = getattr(creator, "email", "") if creator else ""
    reviewed_at = datetime.now().isoformat()
    metadata = dict(existing.get("capaMetadata") or {})
    notification = {"emailSent": False, "recipient": creator_email}

    if requested_status in {"Rejected", "Approved"}:
        decision = "Rejected" if requested_status == "Rejected" else "Approved"
        metadata["lastReview"] = {
            "decision": decision,
            "workflowStatus": new_status,
            "comment": comment,
            "reviewedBy": current_user.username,
            "reviewedAt": reviewed_at,
            "routedTo": creator_username if requested_status == "Rejected" else "",
            "recipientEmail": creator_email if requested_status == "Rejected" else "",
            "eSignature": esign,
        }
        metadata.setdefault("electronicSignatures", []).append({
            **esign,
            "decision": decision,
            "capaId": capa_id,
        })

    capa = update_capa_status(
        capa_id,
        new_status,
        rejected_by=current_user.username,
        rejection_comment=comment,
        capa_metadata=metadata,
    )
    if not capa:
        return jsonify({"error": f"CAPA {capa_id} not found"}), 404

    if requested_status == "Rejected":
        subject = f"CAPA {capa_id} requires correction"
        message = (
            f"CAPA {capa_id} was rejected by {current_user.full_name or current_user.username} "
            f"and routed back to {creator_username or 'the CAPA creator'} for correction.\n\n"
            f"Source record: {capa.get('sourceRecordId')}\n"
            f"Reason: {comment or 'No rejection reason provided.'}\n"
            "Please review the CAPA draft and resubmit it for approval."
        )
        notification["emailSent"] = send_email_notification(
            creator_email,
            subject,
            message,
            run_id=f"capa-review-{capa_id}",
            details={
                "capaId": capa_id,
                "sourceRecordId": capa.get("sourceRecordId"),
                "decision": "Rejected",
                "workflowStatus": new_status,
                "reviewedBy": current_user.username,
            },
        )
    elif requested_status == "Approved":
        subject = f"CAPA {capa_id} approved"
        message = (
            f"CAPA {capa_id} was approved by {current_user.full_name or current_user.username}.\n\n"
            f"Source record: {capa.get('sourceRecordId')}\n"
            f"Comment: {comment or 'No approval comment provided.'}"
        )
        notification["emailSent"] = send_email_notification(
            creator_email,
            subject,
            message,
            run_id=f"capa-review-{capa_id}",
            details={
                "capaId": capa_id,
                "sourceRecordId": capa.get("sourceRecordId"),
                "decision": "Approved",
                "workflowStatus": new_status,
                "reviewedBy": current_user.username,
            },
        )

    log(ACTION_CAPA_STATUS_CHANGE,
        performed_by=current_user.username,
        performed_by_role=current_user.role,
        capa_id=capa_id,
        record_id=capa.get("sourceRecordId"),
        entity_type="capa",
        field_name="status",
        old_value=old_status,
        new_value=new_status,
        notes=(
            f"CAPA {capa_id} rejected and routed to {creator_username or 'creator'}"
            if requested_status == "Rejected"
            else f"CAPA {capa_id} status changed by {current_user.username}"
        ),
        ip_address=request.remote_addr)
    return jsonify({
        "capaId":    capa_id,
        "status":    new_status,
        "requestedStatus": requested_status,
        "message": (
            f"CAPA {capa_id} routed back to {creator_username or 'creator'} for correction"
            if requested_status == "Rejected"
            else f"CAPA {capa_id} status changed to {new_status}"
        ),
        "notification": notification,
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
    except Exception:
        logger.exception("capa.inquire_failed")
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
        except Exception as exc:
            logger.exception("capa.rag_similar_failed")
            return jsonify({"similar": [], "count": 0, "error": str(exc)}), 200
