"""Prometheus /metrics endpoint for the QMS GenAI Platform.

Exposes four families of metrics without depending on the
``prometheus_client`` package — we render the text-exposition
format ourselves so the image stays lean and behaviour is
deterministic under tests.

Metrics
-------
- ``qms_capa_total{status=""}``       CAPAs by workflow status
- ``qms_llm_cost_usd_total``           Sum of LLM $ spend in the window
- ``qms_llm_calls_total{provider="",model="",success=""}`` Call counts
- ``qms_dlq_depth``                    Rows in qms_agent_deadletter (active)
- ``qms_esignature_total{action=""}``  E-signatures by action
- ``qms_audit_chain_ok``               1 if the audit hash chain verifies, else 0
- ``qms_esignature_chain_ok``          1 if the e-sig hash chain verifies, else 0

Grafana consumes this via a Prometheus scrape target pointing at
``/metrics``. Access is gated behind ``METRICS_VIEW`` in the Flask
blueprint so we don't leak business KPIs to anonymous scrapers.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from flask import Blueprint, Response

from auth.permissions import Permission, requires_permission
from services.logging_config import get_logger

log = get_logger(__name__)
metrics_bp = Blueprint("metrics", __name__)


def _fmt(name: str, value: float, labels: dict | None = None,
         help_text: str = "", metric_type: str = "gauge") -> Iterable[str]:
    """Yield Prometheus text-format lines for a single metric."""
    yield f"# HELP {name} {help_text}"
    yield f"# TYPE {name} {metric_type}"
    if labels:
        label_str = ",".join(f'{k}="{_esc(str(v))}"' for k, v in sorted(labels.items()))
        yield f"{name}{{{label_str}}} {value}"
    else:
        yield f"{name} {value}"


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _capa_counts() -> dict[str, int]:
    try:
        from database import SessionLocal
        from models import CAPARecord
        from sqlalchemy import func

        with SessionLocal() as session:
            rows = (
                session.query(CAPARecord.status, func.count(CAPARecord.id))
                .group_by(CAPARecord.status)
                .all()
            )
        return {r[0] or "unknown": int(r[1] or 0) for r in rows}
    except Exception:
        log.exception("metrics.capa_counts_failed")
        return {}


def _llm_stats(window_hours: int = 24) -> tuple[float, dict[tuple[str, str, bool], int]]:
    try:
        from database import SessionLocal
        from models import LLMCallLog
        from sqlalchemy import func

        since = datetime.utcnow() - timedelta(hours=window_hours)
        with SessionLocal() as session:
            rows = (
                session.query(
                    LLMCallLog.provider,
                    LLMCallLog.model,
                    LLMCallLog.success,
                    func.count(LLMCallLog.id),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0),
                )
                .filter(LLMCallLog.timestamp >= since)
                .group_by(LLMCallLog.provider, LLMCallLog.model, LLMCallLog.success)
                .all()
            )
        total_cost = 0.0
        by_call: dict[tuple[str, str, bool], int] = {}
        for provider, model, success, count, cost in rows:
            by_call[(provider or "unknown", model or "unknown", bool(success))] = int(count or 0)
            total_cost += float(cost or 0)
        return total_cost, by_call
    except Exception:
        log.exception("metrics.llm_stats_failed")
        return 0.0, {}


def _dlq_depth() -> int:
    try:
        from database import SessionLocal
        from models import AgentDeadLetter

        with SessionLocal() as session:
            return (
                session.query(AgentDeadLetter)
                .filter(AgentDeadLetter.requeued_at.is_(None))
                .count()
            )
    except Exception:
        log.exception("metrics.dlq_depth_failed")
        return 0


def _esig_counts() -> dict[str, int]:
    try:
        from database import SessionLocal
        from models import ESignature
        from sqlalchemy import func

        with SessionLocal() as session:
            rows = (
                session.query(ESignature.action, func.count(ESignature.id))
                .group_by(ESignature.action)
                .all()
            )
        return {r[0] or "unknown": int(r[1] or 0) for r in rows}
    except Exception:
        # ESignature table may not exist on legacy deployments — return empty.
        return {}


def _chain_ok(fn) -> int:
    try:
        return 1 if fn().get("ok") else 0
    except Exception:
        return 0


@metrics_bp.route("/metrics")
@requires_permission(Permission.METRICS_VIEW)
def prometheus_metrics():
    lines: list[str] = []

    for status, count in _capa_counts().items():
        lines.extend(_fmt("qms_capa_total", count,
                          labels={"status": status},
                          help_text="Count of CAPA records by workflow status",
                          metric_type="gauge"))

    total_cost, calls = _llm_stats()
    lines.extend(_fmt("qms_llm_cost_usd_total", round(total_cost, 6),
                      help_text="Sum of LLM cost (USD) over the trailing 24h",
                      metric_type="gauge"))
    for (provider, model, success), count in calls.items():
        lines.extend(_fmt("qms_llm_calls_total", count,
                          labels={"provider": provider, "model": model,
                                  "success": "true" if success else "false"},
                          help_text="Count of LLM calls in the trailing 24h",
                          metric_type="counter"))

    lines.extend(_fmt("qms_dlq_depth", _dlq_depth(),
                      help_text="Active rows in the agent dead-letter queue",
                      metric_type="gauge"))

    for action, count in _esig_counts().items():
        lines.extend(_fmt("qms_esignature_total", count,
                          labels={"action": action},
                          help_text="21 CFR Part 11 signatures by action",
                          metric_type="counter"))

    from services.audit_service import verify_audit_chain
    from services.esignature_service import verify_chain as verify_esig_chain

    lines.extend(_fmt("qms_audit_chain_ok",
                      _chain_ok(lambda: verify_audit_chain(limit=500)),
                      help_text="1 if the audit hash chain (last 500 rows) verifies, else 0",
                      metric_type="gauge"))
    lines.extend(_fmt("qms_esignature_chain_ok",
                      _chain_ok(lambda: verify_esig_chain(limit=500)),
                      help_text="1 if the e-signature hash chain verifies, else 0",
                      metric_type="gauge"))

    body = "\n".join(lines) + "\n"
    return Response(body, mimetype="text/plain; version=0.0.4")
