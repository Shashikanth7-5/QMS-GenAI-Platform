# tests/test_capa.py
import json


def test_generate_capa_admin(admin_client, sample_record):
    r = admin_client.post("/api/capa/generate",
        data=json.dumps({"record": sample_record}),
        content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "rootCause" in data
    assert "correctiveAction" in data

def test_generate_capa_quality(quality_client, sample_record):
    r = quality_client.post("/api/capa/generate",
        data=json.dumps({"record": sample_record}),
        content_type="application/json")
    assert r.status_code == 200

def test_generate_capa_user_own_record(user_client):
    """User can generate CAPA only on their own record."""
    rec = {"id":"OWN-001","type":"complaint","createdBy":"shashi",
           "title":"My record","description":"test","priority":"High",
           "sector":"General","site":"Unknown","regulatoryRef":[]}
    r = user_client.post("/api/capa/generate",
        data=json.dumps({"record": rec}),
        content_type="application/json")
    assert r.status_code == 200

def test_generate_capa_user_others_record_blocked(user_client, sample_record):
    """User cannot generate CAPA on records they don't own."""
    r = user_client.post("/api/capa/generate",
        data=json.dumps({"record": sample_record}),   # owned by admin
        content_type="application/json")
    assert r.status_code == 403

def test_save_capa_creates_record(admin_client):
    payload = {
        "sourceRecordId":    "CMP-2024-0891",
        "rootCause":         "Process gap",
        "immediateAction":   "Quarantine",
        "correctiveAction":  "Revise SOP",
        "preventiveAction":  "Training",
        "capaOwner":         "QA Lead",
        "effectivenessCheck":"Monitor 90 days",
        "riskRating":        "High",
        "estimatedClosureDays": 45,
    }
    r = admin_client.post("/api/capa/save",
        data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    data = r.get_json()
    assert "capaId" in data
    assert data["status"] == "Under Review"

def test_approve_capa_admin_only(admin_client, quality_client, user_client):
    # Get a CAPA ID first
    capas = admin_client.get("/api/capas").get_json()["capas"]
    if not capas:
        pytest.skip("No CAPAs to test")
    cid = capas[0]["capaId"]

    # quality cannot approve
    r_q = quality_client.patch(f"/api/capas/{cid}/status",
        data=json.dumps({"status":"Approved"}), content_type="application/json")
    assert r_q.status_code == 403

    # user cannot approve
    r_u = user_client.patch(f"/api/capas/{cid}/status",
        data=json.dumps({"status":"Approved"}), content_type="application/json")
    assert r_u.status_code == 403

def test_run_batch_admin_only(admin_client, quality_client, user_client):
    r_q = quality_client.post("/api/capa/run-batch", content_type="application/json")
    assert r_q.status_code == 403
    r_u = user_client.post("/api/capa/run-batch", content_type="application/json")
    assert r_u.status_code == 403
    r_a = admin_client.post("/api/capa/run-batch", content_type="application/json")
    assert r_a.status_code == 200
    data = r_a.get_json()
    assert "processed" in data
    assert "message" in data

def test_capa_list_user_sees_own_only(user_client):
    r = user_client.get("/api/capas")
    data = r.get_json()
    for c in data["capas"]:
        assert c.get("createdByUsername") == "shashi"
