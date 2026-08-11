def test_readyz_reports_runtime_dependencies(client):
    response = client.get("/readyz")
    assert response.status_code in (200, 503)
    data = response.get_json()
    assert "db" in data
    assert "celery" in data
    assert "smtp" in data
    assert "storage" in data
    assert "hardening" in data
