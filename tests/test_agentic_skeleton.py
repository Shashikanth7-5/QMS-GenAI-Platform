import json


def test_mcp_registry_parses_enabled_servers():
    from services.mcp_registry import enabled_mcp_tools

    raw = json.dumps([
        {
            "name": "salesforce-qms",
            "transport": "http",
            "endpoint": "https://mcp.example.test",
            "authEnv": "SALESFORCE_MCP_TOKEN",
            "scopes": ["quality-records", "capa-sync"],
        },
        {"name": "disabled", "endpoint": "https://disabled.example.test", "enabled": False},
        {"name": "", "endpoint": "https://ignored.example.test"},
    ])

    tools = enabled_mcp_tools(raw)

    assert len(tools) == 1
    assert tools[0]["name"] == "salesforce-qms"
    assert tools[0]["authEnv"] == "SALESFORCE_MCP_TOKEN"
    assert tools[0]["scopes"] == ["quality-records", "capa-sync"]


def test_capa_workflow_falls_back_when_disabled(monkeypatch):
    from services.agents import langgraph_workflow

    called = {}

    class FakeOrchestrator:
        def run(self, record_id, **kwargs):
            called["record_id"] = record_id
            called["kwargs"] = kwargs
            return {"status": "ok", "recordId": record_id, "steps": []}

    monkeypatch.setenv("LANGGRAPH_WORKFLOW_ENABLED", "false")
    monkeypatch.setattr(langgraph_workflow, "CapaAgentOrchestrator", FakeOrchestrator)

    result = langgraph_workflow.run_capa_workflow("QR-1", triggered_by="test")

    assert result["status"] == "ok"
    assert called["record_id"] == "QR-1"
    assert called["kwargs"]["triggered_by"] == "test"


def test_agents_route_uses_workflow_entrypoint(admin_client, monkeypatch):
    import routes.agents as agents_route

    called = {}

    def fake_run(record_id, **kwargs):
        called["record_id"] = record_id
        called["kwargs"] = kwargs
        return {
            "status": "ok",
            "recordId": record_id,
            "requiresHumanApproval": True,
            "steps": [],
        }

    monkeypatch.setattr(agents_route, "run_capa_workflow", fake_run)
    record_id = admin_client.get("/api/records").get_json()["records"][0]["id"]

    response = admin_client.post("/api/agents/capa/run", json={"recordId": record_id})

    assert response.status_code == 200
    assert called["record_id"] == record_id
    assert called["kwargs"]["triggered_by"] == "admin"


def test_langgraph_enabled_runs_graph(admin_client, monkeypatch):
    from services.agents.langgraph_workflow import run_capa_workflow

    monkeypatch.setenv("LANGGRAPH_WORKFLOW_ENABLED", "true")
    record_id = admin_client.get("/api/records").get_json()["records"][0]["id"]

    result = run_capa_workflow(record_id, triggered_by="test")

    assert result["status"] == "ok"
    assert result["recordId"] == record_id
    assert result["agentRunId"].startswith("RUN-")
    assert len(result["steps"]) >= 3
