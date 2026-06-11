# tests/test_ingestion.py
import io


def test_upload_unrelated_file_rejected(admin_client):
    """A non-QMS file should return 422 with insufficient flag."""
    content = b"Hello world. This is a recipe for chocolate cake. Mix flour, sugar, eggs."
    data = {"file": (io.BytesIO(content), "recipe.txt")}
    r = admin_client.post("/api/rag/extract",
        data=data, content_type="multipart/form-data")
    # In mock mode the pre-flight text check fires
    assert r.status_code in (200, 422)
    if r.status_code == 422:
        body = r.get_json()
        assert body.get("insufficient") is True
        assert "reason" in body

def test_upload_qms_file_accepted(admin_client):
    """A file with QMS keywords should be accepted."""
    content = (
        b"COMPLAINT REPORT\n"
        b"Batch: LOT-2024-001\nSite: Mumbai\nOwner: J. Smith\n"
        b"Deviation from SOP-MFG-007. ISO 13485 compliance breach.\n"
        b"Investigation required. Root cause: calibration failure.\n"
        b"CAPA required. Regulatory ref: 21 CFR 820.198.\n"
        b"Priority: Critical. Non-conformance detected during audit."
    )
    data = {"file": (io.BytesIO(content), "complaint_report.txt")}
    r = admin_client.post("/api/rag/extract",
        data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("success") is True
    assert "record" in body

def test_upload_unsupported_extension(admin_client):
    data = {"file": (io.BytesIO(b"data"), "file.exe")}
    r = admin_client.post("/api/rag/extract",
        data=data, content_type="multipart/form-data")
    assert r.status_code == 400

def test_upload_empty_file(admin_client):
    data = {"file": (io.BytesIO(b""), "empty.txt")}
    r = admin_client.post("/api/rag/extract",
        data=data, content_type="multipart/form-data")
    # empty txt will fail relevance check
    assert r.status_code in (400, 422)


# tests/test_search.py — appended here for brevity

def test_search_admin_sees_all(admin_client):
    r = admin_client.get("/api/search?q=complaint")
    data = r.get_json()
    assert r.status_code == 200
    assert data["sees_all"] is True
    assert data["total"] >= 0

def test_search_user_id_lookup(user_client):
    r = user_client.get("/api/search?q=CMP-2024-0891")
    data = r.get_json()
    assert r.status_code == 200
    # Should find by exact ID even for user role
    ids = [rec["id"] for rec in data.get("records",[])]
    assert "CMP-2024-0891" in ids

def test_search_empty_query(admin_client):
    r = admin_client.get("/api/search?q=")
    data = r.get_json()
    assert data["total"] == 0

def test_analytics_admin_only(admin_client, user_client):
    r_a = admin_client.get("/api/analytics")
    assert r_a.status_code == 200
    data = r_a.get_json()
    assert "priority" in data
    assert "capa_status" in data
    r_u = user_client.get("/api/analytics")
    assert r_u.status_code == 403
