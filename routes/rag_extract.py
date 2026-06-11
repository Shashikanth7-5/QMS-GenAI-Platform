# routes/rag_extract.py
import json, os, uuid

from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from services.ingestion_service import process_upload, allowed_file, extract_text
_SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() == "true"

rag_bp = Blueprint("rag", __name__)
_EXTRACTION_STORE: list = []

@rag_bp.route("/rag-extract")
@login_required
def page_rag_extract():
    return render_template("rag_extract.html")   # flat path — no subfolder needed

@rag_bp.route("/api/rag/extract", methods=["POST"])
@login_required
def api_rag_extract():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "Empty file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type.",
                        "supported": ["PDF","Excel","CSV","Word (.docx)","Images","TXT"]}), 400
    try:
        file_bytes  = file.read()
        ext         = file.filename.rsplit(".", 1)[-1].lower()
        raw_content = extract_text(file_bytes, file.filename)
        record      = process_upload(file_bytes, file.filename)
        text_preview = raw_content[:800].strip() if isinstance(raw_content, str) else ""
        extraction = {
            "id":          f"EXT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}",
            "filename":    file.filename,
            "fileType":    ext.upper(),
            "fileSize":    len(file_bytes),
            "extractedAt": datetime.now().isoformat(),
            "extractedBy": current_user.username,
            "record":      record,
            "textPreview": text_preview,
            "isImage":     isinstance(raw_content, dict),
        }
        _EXTRACTION_STORE.append(extraction)
        return jsonify({**extraction, "message": f"Extracted from {file.filename}"})
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500

@rag_bp.route("/api/rag/ask", methods=["POST"])
@login_required
def api_rag_ask():
    body = request.get_json(force=True) or {}
    extraction_id = body.get("extractionId", "")
    question = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "Missing question"}), 400
    extraction = next((e for e in _EXTRACTION_STORE if e["id"] == extraction_id), None)
    if not extraction:
        return jsonify({"error": "Extraction not found"}), 404
    if extraction["extractedBy"] != current_user.username and not current_user.is_admin():
        return jsonify({"error": "Not authorised"}), 403
    record = extraction.get("record", {})
    prompt = (
        "You are a QMS document analyst for Life Sciences.\n\n"
        f"DOCUMENT: {extraction['filename']}\n"
        f"Record: {record.get('id')} | {record.get('type','').upper()} | {record.get('priority')}\n"
        f"Title: {record.get('title')}\nDescription: {record.get('description')}\n"
        f"Regulations: {', '.join(record.get('regulatoryRef', []))}\n"
        f"Text excerpt: {extraction.get('textPreview','')}\n\n"
        f"QUESTION: {question}\n\nAnswer concisely based only on the document context above."
    )
    try:
        from services.ai_service import MOCK_MODE, AI_PROVIDER, AI_API_KEY
        if MOCK_MODE or AI_PROVIDER == "mock" or not AI_API_KEY:
            answer = f"[Mock] Based on '{extraction['filename']}': {record.get('description','N/A')}"
        else:
            import httpx
            from services.ai_service import _build_request, _extract_text
            headers, payload, url = _build_request(prompt)
            payload["max_tokens"] = 800
            resp = httpx.post(url, headers=headers, json=payload, timeout=60.0, verify=_SSL_VERIFY)
            resp.raise_for_status()
            answer = _extract_text(resp.json())
        return jsonify({"extractionId": extraction_id, "question": question,
                        "answer": answer, "answeredAt": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@rag_bp.route("/api/rag/history")
@login_required
def api_rag_history():
    history = _EXTRACTION_STORE if current_user.is_admin() else \
              [e for e in _EXTRACTION_STORE if e["extractedBy"] == current_user.username]
    return jsonify({"history": [{"id":e["id"],"filename":e["filename"],"fileType":e["fileType"],
        "fileSize":e["fileSize"],"extractedAt":e["extractedAt"],"extractedBy":e["extractedBy"],
        "recordTitle":e["record"].get("title",""),"recordType":e["record"].get("type",""),
        "isImage":e["isImage"]} for e in reversed(history)], "total": len(history)})

@rag_bp.route("/api/rag/history/<ext_id>", methods=["DELETE"])
@login_required
def api_delete_extraction(ext_id):
    extraction = next((e for e in _EXTRACTION_STORE if e["id"] == ext_id), None)
    if not extraction: return jsonify({"error": "Not found"}), 404
    if extraction["extractedBy"] != current_user.username and not current_user.is_admin():
        return jsonify({"error": "Not authorised"}), 403
    _EXTRACTION_STORE.remove(extraction)
    return jsonify({"deleted": ext_id})
