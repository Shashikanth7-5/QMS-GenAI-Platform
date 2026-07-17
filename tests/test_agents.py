def _first_record_id(client):
    data = client.get("/api/records").get_json()
    records = data if isinstance(data, list) else data.get("records", [])
    assert records
    return records[0]["id"]


def test_record_intake_agent(admin_client):
    record_id = _first_record_id(admin_client)
    r = admin_client.post("/api/agents/record/intake", json={"recordId": record_id})
    assert r.status_code == 200
    data = r.get_json()
    assert data["agent"] == "record_intake_agent"
    assert data["data"]["record"]["id"] == record_id


def test_decision_agent(admin_client):
    record_id = _first_record_id(admin_client)
    r = admin_client.post("/api/agents/decision/check", json={"recordId": record_id})
    assert r.status_code == 200
    data = r.get_json()
    assert data["agent"] == "decision_eligibility_agent"
    assert "decision" in data["data"]


def test_rca_scoring_agent(admin_client):
    record_id = _first_record_id(admin_client)
    r = admin_client.post("/api/agents/rca/score", json={"recordId": record_id})
    assert r.status_code == 200
    data = r.get_json()
    assert data["agent"] == "rca_scoring_agent"
    assert "overall_score" in data["data"]["score"]


def test_capa_agent_orchestrator(admin_client):
    record_id = _first_record_id(admin_client)
    r = admin_client.post("/api/agents/capa/run", json={"recordId": record_id})
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["requiresHumanApproval"] is True
    assert len(data["steps"]) >= 3


def test_admin_access_agent_admin_only(admin_client, user_client):
    r_user = user_client.post("/api/agents/admin/access-review")
    assert r_user.status_code == 403
    r_admin = admin_client.post("/api/agents/admin/access-review")
    assert r_admin.status_code == 200
    assert r_admin.get_json()["agent"] == "admin_access_agent"
