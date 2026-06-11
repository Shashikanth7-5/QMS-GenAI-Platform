# routes/rag.py
# GET  /rag-extract          → dedicated RAG Extract page
# POST /api/rag/extract      → same as upload but standalone
# GET  /api/rag/records      → all uploaded records (role-filtered)

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from services.ingestion_service import process_upload, allowed_file
from data.records import (
    add_uploaded_record, get_all_records, get_records_by_owner,
)

rag_bp = Blueprint("rag", __name__)


@rag_bp.route("/rag-extract")
@login_required
def page_rag():
    return render_template("rag/index.html")


@rag_bp.route("/api/rag/extract", methods=["POST"])
@login_required
def api_rag_extract():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Empty file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400

    try:
        file_bytes = file.read()
        record     = process_upload(file_bytes, file.filename)

        if record.get("_insufficient"):
            return jsonify({
                "success":      False,
                "insufficient": True,
                "reason":       record.get("reason","Document does not contain QMS data."),
            }), 422

        record["createdBy"]     = current_user.username
        record["createdByName"] = current_user.full_name
        record["createdByRole"] = current_user.role

        saved = add_uploaded_record(record)
        return jsonify({"success": True, "record": saved,
                        "message": f"Record {saved['id']} extracted."})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500


@rag_bp.route("/api/rag/records", methods=["GET"])
@login_required
def api_rag_records():
    if current_user.sees_all_records():
        recs = [r for r in get_all_records() if r.get("_source") == "uploaded"]
    else:
        recs = [r for r in get_records_by_owner(current_user.username)
                if r.get("_source") == "uploaded"]
    return jsonify({"records": recs, "total": len(recs)})
@rag_bp.route("/salesforce-demo")
@login_required
def page_salesforce_demo():
    return render_template("salesforce_demo.html")