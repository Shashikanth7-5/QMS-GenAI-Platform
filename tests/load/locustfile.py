"""Locust load test for the QMS GenAI Platform.

Two user classes:
- AnonymousUser  : probes /healthz and /readyz to stress the liveness path
- TenantUser     : authenticated API-key traffic against /api/v1/records list
                   and /api/v1/capa/generate with idempotency keys

Target scenario (see README.md next to this file):
    100 concurrent users, 30s ramp, 5m duration

Environment variables:
    QMS_HOST     - base URL, e.g. https://qms.example.com  (overridden by --host)
    QMS_TENANT   - tenant identifier sent in X-Tenant-ID
    QMS_API_KEY  - per-tenant API key sent in X-API-Key

Do NOT run this in CI - it requires a live app.
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task, tag


QMS_TENANT = os.getenv("QMS_TENANT", "demo-tenant")
QMS_API_KEY = os.getenv("QMS_API_KEY", "changeme-demo-key")


class AnonymousUser(HttpUser):
    """Unauthenticated probes against the health endpoints."""

    weight = 1
    wait_time = between(1, 3)

    @tag("health")
    @task(3)
    def healthz(self) -> None:
        self.client.get("/healthz", name="/healthz")

    @tag("health")
    @task(2)
    def readyz(self) -> None:
        self.client.get("/readyz", name="/readyz")


class TenantUser(HttpUser):
    """Authenticated API-key traffic simulating a real tenant."""

    weight = 4
    wait_time = between(2, 6)

    def on_start(self) -> None:
        self.client.headers.update(
            {
                "X-Tenant-ID": QMS_TENANT,
                "X-API-Key": QMS_API_KEY,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    @tag("records")
    @task(5)
    def list_records(self) -> None:
        self.client.get(
            "/api/v1/records?limit=25",
            name="GET /api/v1/records",
        )

    @tag("capa")
    @task(1)
    def generate_capa(self) -> None:
        idempotency_key = str(uuid.uuid4())
        payload = {
            "recordId": "QR-2026-DEMO-001",
            "sector": "MedDevice",
            "priority": "High",
            "description": (
                "Load-test synthetic event: intermittent sensor drift "
                "observed during batch verification."
            ),
        }
        self.client.post(
            "/api/v1/capa/generate",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
            name="POST /api/v1/capa/generate",
        )
