"""Configurable workflow rules for external QMS integrations.

The default file is ``agent_workflows.yaml`` at the project root. It is
reloaded when its modified timestamp changes, so admins can adjust record
type aliases or workflow states without changing Python code.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from threading import Lock

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - requirements include PyYAML
    yaml = None


_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PATH = _ROOT / "agent_workflows.yaml"
_LOCK = Lock()
_CACHE = {"path": None, "mtime": None, "config": None}

_DEFAULT_CONFIG = {
    "version": 1,
    "eligible_input_statuses": [
        "Draft Generated", "New", "Open", "Investigation",
        "Investigation Complete", "RCA Complete", "Ready for CAPA",
    ],
    "capa_statuses": {
        "draft_saved": "Under Review",
        "rejected_route_to_creator": "Pending Correction",
        "approved": "Approved",
        "closed": "Closed",
    },
    "external_record_type_map": {
        "complaint": ["complaint", "customer complaint", "product complaint", "case"],
        "deviation": ["deviation", "observation", "quality event", "quality_event", "incident"],
        "cc": ["cc", "change control", "change_control", "change"],
        "nc": ["nc", "nonconformance", "non-conformance", "non conformance"],
        "audit": ["audit", "audit finding", "inspection observation"],
    },
    "decision_source_by_type": {
        "complaint": "complaint",
        "deviation": "deviation",
        "observation": "deviation",
        "cc": "cc",
        "nc": "deviation",
        "audit": "deviation",
    },
    "agent_pipeline": [
        "record_intake_agent",
        "decision_eligibility_agent",
        "rca_scoring_agent",
        "capa_draft_agent",
    ],
    "esign": {
        "required_for": ["Approved", "Rejected"],
        "basis": ["21 CFR Part 11", "EU Annex 11"],
    },
    "notifications": {"on_rejection": True, "on_approval": True},
}


def _config_path() -> Path:
    configured = os.getenv("AGENT_WORKFLOW_CONFIG", "").strip()
    return Path(configured) if configured else _DEFAULT_PATH


def _merge(default: dict, override: dict) -> dict:
    result = copy.deepcopy(default)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_workflow_config() -> dict:
    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    with _LOCK:
        if _CACHE["config"] is not None and _CACHE["path"] == str(path) and _CACHE["mtime"] == mtime:
            return copy.deepcopy(_CACHE["config"])

        loaded = {}
        if path.exists() and yaml is not None:
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
        config = _merge(_DEFAULT_CONFIG, loaded)
        _CACHE.update({"path": str(path), "mtime": mtime, "config": config})
        return copy.deepcopy(config)


def workflow_snapshot() -> dict:
    config = load_workflow_config()
    return {
        "version": config.get("version"),
        "configPath": str(_config_path()),
        "eligibleInputStatuses": config.get("eligible_input_statuses", []),
        "capaStatuses": config.get("capa_statuses", {}),
        "recordTypeMap": config.get("external_record_type_map", {}),
        "decisionSourceByType": config.get("decision_source_by_type", {}),
        "agentPipeline": config.get("agent_pipeline", []),
        "esign": config.get("esign", {}),
    }


def normalize_record_type(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "deviation"
    config = load_workflow_config()
    for canonical, aliases in config.get("external_record_type_map", {}).items():
        choices = {canonical.lower(), *[str(alias).lower() for alias in aliases or []]}
        if raw in choices:
            return canonical
    return raw.replace(" ", "_")


def decision_source_for(record_type: str) -> str:
    canonical = normalize_record_type(record_type)
    mapped = load_workflow_config().get("decision_source_by_type", {}).get(canonical, canonical)
    return mapped if mapped in {"complaint", "deviation", "cc"} else "deviation"


def is_agent_eligible(record: dict) -> tuple[bool, str]:
    status = (record.get("status") or "Draft Generated").strip()
    eligible = set(load_workflow_config().get("eligible_input_statuses", []))
    if status in eligible:
        return True, "eligible"
    return False, f"Record status '{status}' is not configured for AI CAPA creation"


def capa_status(name: str, default: str) -> str:
    return load_workflow_config().get("capa_statuses", {}).get(name, default)
