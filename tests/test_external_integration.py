def test_api_workflow_config(client):
    response = client.get("/api/v1/workflow-config")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "eligibleInputStatuses" in data
    assert "agentPipeline" in data
    assert "Approved" in data["esign"]["required_for"]


def test_external_quality_event_capa_runs_agents(client):
    payload = {
        "externalSystem": "salesforce",
        "objectType": "Quality_Event__c",
        "user": {
            "username": "sf.quality.lead",
            "email": "quality.lead@example.com",
            "role": "Quality Lead",
        },
        "record": {
            "id": "SF-QE-9001",
            "category": "Complaint",
            "status": "Open",
            "title": "Device complaint with patient impact",
            "description": "Customer reported device malfunction with patient safety impact and recall assessment.",
            "priority": "High",
            "sector": "Medical Device",
            "site": "Site A",
            "regulatoryRef": ["21 CFR 820.198", "EU MDR 2017/745 Article 87"],
        },
        "options": {"saveDraft": True},
    }
    response = client.post("/api/v1/integrations/quality-event/capa", json=payload)
    assert response.status_code in (200, 201)
    data = response.get_json()["data"]
    assert data["integrationStatus"] == "completed"
    assert data["record"]["id"] == "SF-QE-9001"
    assert data["record"]["type"] == "complaint"
    assert data["agentRun"]["capaTriggered"] is True
    assert data["capa"]["saved"]["capaId"]
    assert data["ui"]["manualFallbackAvailable"] is True


def test_external_quality_event_skips_unconfigured_state(client):
    payload = {
        "externalSystem": "trackwise",
        "user": {"username": "tw.user", "email": "tw.user@example.com"},
        "record": {
            "id": "TW-QE-9002",
            "category": "Deviation",
            "status": "Closed",
            "title": "Closed deviation",
            "description": "A closed event should not trigger agents unless forced.",
            "priority": "Medium",
            "sector": "BioPharma",
        },
    }
    response = client.post("/api/v1/integrations/quality-event/capa", json=payload)
    assert response.status_code == 202
    data = response.get_json()["data"]
    assert data["integrationStatus"] == "skipped"
    assert data["ui"]["allowManualFallback"] is True
