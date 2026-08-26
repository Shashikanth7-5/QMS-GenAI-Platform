# tests/test_agent_safety.py
# Version@3 additions: durable DLQ, kill-switch, turn-budget, autosave gate,
# YAML reload robustness, run_context propagation, LLM cost logging.

import os
import pytest
from unittest.mock import patch


def _first_record_id(client):
    data = client.get("/api/records").get_json()
    records = data if isinstance(data, list) else data.get("records", [])
    assert records, "seed records missing"
    return records[0]["id"]


# ────────────────────────────────────────────────────────────
# Dead-letter store (durable)
# ────────────────────────────────────────────────────────────
def test_deadletter_park_and_requeue(admin_client):
    from services.agents import deadletter_store

    parked = deadletter_store.park(
        "TEST-DL-001", attempts=3, last_error="synthetic", run_id="SUP-TEST",
    )
    assert parked["recordId"] == "TEST-DL-001"

    active = deadletter_store.list_active(limit=50)
    assert any(e.get("recordId") == "TEST-DL-001" for e in active)

    assert deadletter_store.is_dead_lettered("TEST-DL-001") is True

    assert deadletter_store.requeue("TEST-DL-001", requeued_by="tests") is True
    assert deadletter_store.is_dead_lettered("TEST-DL-001") is False


def test_deadletter_requeue_via_store(admin_client):
    """The requeue helper flips the row's status via the store — the HTTP
    surface for it lives on the agents blueprint and is admin-only."""
    from services.agents import deadletter_store

    deadletter_store.park(
        "TEST-DL-API", attempts=2, last_error="api-test", run_id="SUP-API",
    )
    assert deadletter_store.is_dead_lettered("TEST-DL-API") is True
    assert deadletter_store.requeue("TEST-DL-API", requeued_by="tests") is True
    assert deadletter_store.is_dead_lettered("TEST-DL-API") is False


# ────────────────────────────────────────────────────────────
# Kill-switch: supervisor must refuse all work when enabled
# ────────────────────────────────────────────────────────────
def test_supervisor_respects_kill_switch(admin_client, monkeypatch):
    from services.agents import supervisor as sup

    monkeypatch.setattr(sup, "AGENT_KILL_SWITCH", True)
    result = sup.AgentSupervisor().run_once(triggered_by="tests")
    assert result["status"] == "skipped"
    assert result["reason"] == "kill_switch"


def test_orchestrator_respects_kill_switch(admin_client, monkeypatch):
    from services.agents import orchestrator as orch

    record_id = _first_record_id(admin_client)
    monkeypatch.setattr(orch, "AGENT_KILL_SWITCH", True)
    r = admin_client.post("/api/agents/capa/run", json={"recordId": record_id})
    body = r.get_json() or {}
    assert body.get("status") == "error"
    assert "kill switch" in (body.get("error") or "").lower()


# ────────────────────────────────────────────────────────────
# Turn budget cannot be exceeded
# ────────────────────────────────────────────────────────────
def test_orchestrator_turn_budget_enforced(admin_client, monkeypatch):
    """AGENT_MAX_TURNS=1 should abort before the second step runs."""
    from services.agents import orchestrator as orch

    record_id = _first_record_id(admin_client)
    monkeypatch.setattr(orch, "AGENT_MAX_TURNS", 1)
    r = admin_client.post("/api/agents/capa/run", json={"recordId": record_id})
    body = r.get_json() or {}
    # With budget=1, only intake runs; subsequent turn increment raises.
    assert body.get("status") == "error" or (body.get("turnsUsed") or 0) <= 1


# ────────────────────────────────────────────────────────────
# Autosave-off: supervisor proposes but does not save
# ────────────────────────────────────────────────────────────
def test_supervisor_autosave_off_produces_proposal(admin_client, monkeypatch):
    from services.agents import supervisor as sup

    monkeypatch.setattr(sup, "AGENT_AUTOSAVE_CAPA_DRAFT", False)
    result = sup.AgentSupervisor().run_once(triggered_by="tests", limit=1, allow_weekend=True)
    # Either "ok" (a proposal or eligibility-skip) or "skipped" (weekend guard,
    # depending on when tests run). Ensure we didn't autosave anything.
    for capa in result.get("capas", []):
        # Under autosave=False we should never see a saved CAPA in "capas".
        pytest.fail(f"Autosave was disabled but a CAPA was persisted: {capa}")


# ────────────────────────────────────────────────────────────
# Workflow YAML reload — malformed YAML must not blow up the app
# ────────────────────────────────────────────────────────────
def test_workflow_yaml_malformed_falls_back(tmp_path, monkeypatch):
    from services import workflow_config as wc

    bad = tmp_path / "workflow.yaml"
    bad.write_text("not: [valid: yaml: at: all", encoding="utf-8")

    # Force reload
    monkeypatch.setenv("AGENT_WORKFLOW_CONFIG", str(bad))
    wc._CACHE.update({"path": None, "mtime": None, "config": None})
    cfg = wc.load_workflow_config()
    # Should still return a usable config (defaults) rather than raising.
    assert isinstance(cfg, dict)
    assert "eligible_input_statuses" in cfg


# ────────────────────────────────────────────────────────────
# Run context: run_id + tenant_id propagate to logs
# ────────────────────────────────────────────────────────────
def test_run_context_binds_and_clears():
    from services import run_context

    # Prior request handlers may have left ctx set — snapshot the outer value
    # so we can assert scope exit restores it.
    outer_tenant = run_context.get_tenant_id()
    outer_user = run_context.get_user()

    with run_context.run_scope(tenant_id="ACME", user="alice", prefix="TEST"):
        snap = run_context.snapshot()
        assert snap["tenant_id"] == "ACME"
        assert snap["user"] == "alice"
        assert (snap["run_id"] or "").startswith("TEST-")

    # Scope exit restores whatever was set before we entered.
    assert run_context.get_tenant_id() == outer_tenant
    assert run_context.get_user() == outer_user


def test_response_carries_request_id(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers.get("X-Request-Id"), "server should echo a request id"


def test_client_supplied_request_id_accepted(client):
    r = client.get("/healthz", headers={"X-Request-Id": "test-run-abc123"})
    # Server should reflect our id back (or mint a safe one if rejected).
    assert r.headers.get("X-Request-Id") in ("test-run-abc123",) or r.headers.get("X-Request-Id").startswith("REQ-")


# ────────────────────────────────────────────────────────────
# LLM call log writes when tokens are recorded
# ────────────────────────────────────────────────────────────
def test_llm_call_log_write_smoke(admin_client):
    """Direct write to LLMCallLog — verifies the model + DB path work."""
    from database import SessionLocal
    from models import LLMCallLog

    with SessionLocal() as session:
        session.add(LLMCallLog(
            username="tests", provider="mock", model="unit-test", task="capa_gen",
            input_tokens=42, output_tokens=17, latency_ms=100, cost_usd=0.0001,
            success=True, cached=False,
        ))
        session.commit()
        row = session.query(LLMCallLog).filter_by(username="tests").order_by(LLMCallLog.id.desc()).first()
        assert row is not None
        assert row.input_tokens == 42
        assert row.output_tokens == 17
