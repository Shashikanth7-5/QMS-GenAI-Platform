"""Tests for the improvement-v1 RBAC + 21 CFR Part 11 additions.

Covers:
- auth.permissions.has_permission across the four capability roles
- @requires_permission decorator returns 403 with the missing perm list
- CAPA close now requires e-signature (previously plain admin-only)
- CAPA approve/reject persist a row into qms_esignatures
- verify_chain reports ok=True after a fresh signing
- /metrics returns 401/403 to unauthenticated users
- /metrics returns Prometheus text-format when authorised
"""

from __future__ import annotations

import pytest

from auth.permissions import (
    Permission,
    has_permission,
    ROLE_CAPABILITIES,
    user_capabilities,
)


# ── Pure capability layer (no HTTP) ────────────────────────

class _FakeUser:
    def __init__(self, role, authenticated=True):
        self.role = role
        self.is_authenticated = authenticated


def test_admin_has_every_permission():
    u = _FakeUser("admin")
    for p in Permission:
        assert has_permission(u, p), f"admin missing {p}"


def test_qa_manager_can_close_but_site_lead_cannot():
    manager = _FakeUser("quality")   # legacy alias for qa_manager
    lead = _FakeUser("user")         # legacy alias for site_lead
    assert has_permission(manager, Permission.CAPA_CLOSE)
    assert not has_permission(lead, Permission.CAPA_CLOSE)


def test_qa_reviewer_can_review_but_not_close_or_batch():
    reviewer = _FakeUser("qa_reviewer")
    assert has_permission(reviewer, Permission.CAPA_REVIEW)
    assert not has_permission(reviewer, Permission.CAPA_CLOSE)
    assert not has_permission(reviewer, Permission.CAPA_BATCH_RUN)


def test_unauthenticated_user_has_nothing():
    u = _FakeUser("admin", authenticated=False)
    assert not has_permission(u, Permission.CAPA_REVIEW)


def test_permission_accepts_string_form_from_templates():
    u = _FakeUser("admin")
    assert has_permission(u, "capa:review")
    assert not has_permission(u, "not-a-real-permission")


def test_user_capabilities_returns_sorted_strings():
    caps = user_capabilities(_FakeUser("qa_reviewer"))
    assert caps == sorted(caps)
    assert "capa:review" in caps


# ── HTTP: decorator returns 403 with the missing perm list ──

def test_capa_batch_denied_for_site_lead(user_client):
    resp = user_client.post("/api/capa/run-batch")
    # 403 with our decorator payload, or redirect to /login for unauth
    assert resp.status_code in (302, 403)
    if resp.status_code == 403:
        body = resp.get_json()
        assert "capa:batch" in body.get("missingPermissions", [])


# ── E-signature: closing a CAPA now requires the signature ──

def _seed_capa(sample_record, capa_id, status="Approved"):
    from data.records import add_uploaded_record, get_record_by_id, save_capa
    if not get_record_by_id(sample_record["id"]):
        add_uploaded_record(sample_record)
    save_capa({
        "capaId": capa_id, "status": status,
        "sourceRecordId": sample_record["id"],
        "rootCause": "test",
        "correctiveAction": "test",
        "preventiveAction": "test",
        "createdByUsername": "admin",
    })


def test_capa_close_requires_esignature(admin_client, sample_record):
    capa_id = "CAPA-TEST-CLOSE-001"
    _seed_capa(sample_record, capa_id)
    resp = admin_client.patch(
        f"/api/capas/{capa_id}/status",
        json={"status": "Closed"},   # no eSignature — should fail
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "signature required" in body.get("error", "").lower() or \
           "signature" in body.get("message", "").lower()


def test_capa_approve_persists_signature_row(admin_client, sample_record):
    from services.esignature_service import signatures_for_entity

    capa_id = "CAPA-TEST-SIGN-001"
    _seed_capa(sample_record, capa_id, status="Under Review")
    resp = admin_client.patch(
        f"/api/capas/{capa_id}/status",
        json={
            "status": "Approved",
            "comment": "looks good",
            "eSignature": {
                "password": "admin",
                "meaning": "I approve this CAPA.",
                "reasonCode": "capa_approve",
                "reasonText": "Root cause is well documented.",
            },
        },
    )
    assert resp.status_code == 200, resp.get_json()
    sigs = signatures_for_entity("capa", capa_id)
    assert len(sigs) >= 1
    sig = sigs[-1]
    assert sig["action"] == "capa_approve"
    assert sig["signerUsername"] == "admin"
    assert sig["rowHash"]  # chain populated
    assert "Part 11" in " ".join(sig.get("basis", []))


def test_esignature_chain_verifies_ok(admin_client, sample_record):
    # Trigger at least one signature so the chain is non-empty.
    from services.esignature_service import verify_chain

    capa_id = "CAPA-TEST-CHAIN-001"
    _seed_capa(sample_record, capa_id, status="Under Review")
    admin_client.patch(f"/api/capas/{capa_id}/status", json={
        "status": "Approved",
        "eSignature": {"password": "admin", "meaning": "chain test",
                       "reasonCode": "capa_approve",
                       "reasonText": "chain-test"},
    })
    result = verify_chain(limit=100)
    assert result["ok"] is True, result
    assert result["checked"] >= 1


# ── /metrics endpoint gating ──

def test_metrics_requires_authentication(client):
    resp = client.get("/metrics")
    # 302 (redirect to /login) or 401/403
    assert resp.status_code in (302, 401, 403)


def test_metrics_returns_prometheus_text_for_admin(admin_client):
    resp = admin_client.get("/metrics")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "# TYPE" in body
    assert "qms_" in body
    # Ensure at least the chain gauges are present.
    assert "qms_audit_chain_ok" in body
