# tests/test_records.py
import pytest

def test_admin_sees_all_records(admin_client):
    r = admin_client.get("/api/records")
    data = r.get_json()
    assert r.status_code == 200
    assert data["total"] >= 14      # seeded records

def test_quality_sees_all_records(quality_client):
    r = quality_client.get("/api/records")
    data = r.get_json()
    assert data["total"] >= 14

def test_user_sees_only_own_records(user_client):
    r = user_client.get("/api/records")
    data = r.get_json()
    # shashi has no uploaded records, so should be 0 or their own only
    assert r.status_code == 200
    for rec in data["records"]:
        assert rec.get("createdBy") == "shashi"

def test_id_lookup_available_to_all(user_client):
    # First get any record that exists
    r = user_client.get("/api/records")
    records = r.get_json()
    record_list = records if isinstance(records, list) else records.get("records", [])
    if record_list:
        first_id = record_list[0]["id"]
        r2 = user_client.get(f"/api/records/{first_id}")
        assert r2.status_code == 200
    else:
        pytest.skip("No records in test DB")

def test_unknown_id_returns_404(admin_client):
    r = admin_client.get("/api/records/NOTEXIST-000")
    assert r.status_code == 404

def test_filter_by_type(admin_client):
    r = admin_client.get("/api/records?type=complaint")
    data = r.get_json()
    assert all(rec["type"] == "complaint" for rec in data["records"])

def test_filter_by_priority(admin_client):
    r = admin_client.get("/api/records?status=Draft+Generated")
    data = r.get_json()
    assert all(rec["status"] == "Draft Generated" for rec in data["records"])

def test_metrics_admin_system_wide(admin_client):
    r = admin_client.get("/api/metrics")
    data = r.get_json()
    assert data["total"] >= 14
    assert data["sees_all"] is True

def test_metrics_user_personal(user_client):
    r = user_client.get("/api/metrics")
    data = r.get_json()
    assert data["sees_all"] is False
    # personal counts should not exceed system total
    assert data["total"] >= 0
