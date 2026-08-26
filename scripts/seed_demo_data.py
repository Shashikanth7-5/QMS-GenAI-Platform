"""Seed a small set of demo QMS records + CAPAs so a fresh clone can run
the app end-to-end without needing to hand-craft data.

Idempotent: each record / CAPA is checked by primary key before insert.

Run:
    python -m scripts.seed_demo_data
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from database import SessionLocal, init_db
from models import CAPARecord, QualityRecord
from services.logging_config import get_logger

log = get_logger(__name__)


def _age_days(detected: str) -> int:
    try:
        d = datetime.strptime(detected, "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 0


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

_TODAY = date.today()


def _d(days_ago: int) -> str:
    return (_TODAY - timedelta(days=days_ago)).isoformat()


DEMO_RECORDS: list[dict] = [
    {
        "id": "QR-2026-DEMO-001",
        "type": "complaint",
        "sector": "Medical Device",
        "title": "Sterility failure - lot MD-DEMO-A",
        "description": "Sterility test failure detected on finished-product lot MD-DEMO-A during QC release testing. Two positive growth results out of 10 samples.",
        "priority": "Critical",
        "status": "Draft Generated",
        "site": "Site A - Chennai",
        "owner": "R. Patel",
        "detected_date": _d(21),
        "product_family": "Cardiac catheters",
        "batch_lot": "MD-DEMO-A",
        "regulatory_refs": ["21 CFR Part 820", "ISO 13485:2016"],
    },
    {
        "id": "QR-2026-DEMO-002",
        "type": "deviation",
        "sector": "BioPharma",
        "title": "Temperature excursion - cold storage 3B",
        "description": "Cold storage unit 3B recorded 8-12 C for approximately 4 hours due to compressor malfunction.",
        "priority": "High",
        "status": "Draft Generated",
        "site": "Site B - Mumbai",
        "owner": "A. Sharma",
        "detected_date": _d(18),
        "product_family": "Biologic drug substance",
        "batch_lot": "BP-DEMO-17",
        "regulatory_refs": ["21 CFR Part 211", "ICH Q1A"],
    },
    {
        "id": "QR-2026-DEMO-003",
        "type": "cc",
        "sector": "Medical Device",
        "title": "Raw material supplier change - catheter tubing",
        "description": "Proposed change of primary raw material supplier for catheter tubing due to supply chain constraints.",
        "priority": "Medium",
        "status": "Draft Generated",
        "site": "Site A - Chennai",
        "owner": "S. Kumar",
        "detected_date": _d(15),
        "product_family": "Catheters",
        "batch_lot": "",
        "regulatory_refs": ["21 CFR 820.70", "ISO 13485 7.4"],
    },
    {
        "id": "QR-2026-DEMO-004",
        "type": "complaint",
        "sector": "BioPharma",
        "title": "Particulate matter observed in injectable",
        "description": "Customer complaint of visible particulate matter in injectable product vial.",
        "priority": "Critical",
        "status": "Under Review",
        "site": "Site C - Hyderabad",
        "owner": "M. Reddy",
        "detected_date": _d(12),
        "product_family": "Sterile injectables",
        "batch_lot": "BP-DEMO-22",
        "regulatory_refs": ["21 CFR 211.192", "USP 788"],
    },
    {
        "id": "QR-2026-DEMO-005",
        "type": "nc",
        "sector": "Medical Device",
        "title": "Dimensional out-of-spec - titanium implant",
        "description": "Incoming inspection identified dimensional non-conformance on titanium implant components (3 of 50).",
        "priority": "High",
        "status": "Draft Generated",
        "site": "Site A - Chennai",
        "owner": "P. Nair",
        "detected_date": _d(10),
        "product_family": "Orthopedic implants",
        "batch_lot": "MD-DEMO-IMP-7",
        "regulatory_refs": ["ISO 13485 8.3", "ASTM F136"],
    },
    {
        "id": "QR-2026-DEMO-006",
        "type": "audit",
        "sector": "BioPharma",
        "title": "GMP audit finding - documentation gaps",
        "description": "Internal GMP audit identified gaps in batch record documentation practices.",
        "priority": "Medium",
        "status": "Draft Generated",
        "site": "Site B - Mumbai",
        "owner": "K. Singh",
        "detected_date": _d(8),
        "product_family": "Biologic drug product",
        "batch_lot": "",
        "regulatory_refs": ["21 CFR 211.68", "EU GMP Ch. 4"],
    },
    {
        "id": "QR-2026-DEMO-007",
        "type": "deviation",
        "sector": "Medical Device",
        "title": "Calibration overdue on 3 critical devices",
        "description": "Routine equipment audit identified 3 critical measurement devices past their scheduled calibration dates.",
        "priority": "Medium",
        "status": "Draft Generated",
        "site": "Site D - Bangalore",
        "owner": "V. Rao",
        "detected_date": _d(6),
        "product_family": "Diagnostic equipment",
        "batch_lot": "",
        "regulatory_refs": ["ISO 13485 7.6", "21 CFR 820.72"],
    },
    {
        "id": "QR-2026-DEMO-008",
        "type": "complaint",
        "sector": "BioPharma",
        "title": "Label misprint - dosage information",
        "description": "Post-market surveillance identified incorrect dosage information on product labels; single batch impact.",
        "priority": "High",
        "status": "Approved",
        "site": "Site C - Hyderabad",
        "owner": "D. Mehta",
        "detected_date": _d(45),
        "product_family": "Oral solid dose",
        "batch_lot": "BP-DEMO-31",
        "regulatory_refs": ["21 CFR Part 201", "EU FMD 2011/62"],
    },
    {
        "id": "QR-2026-DEMO-009",
        "type": "cc",
        "sector": "BioPharma",
        "title": "Fermentation parameter change - yield uplift",
        "description": "Proposed change to fermentation process parameters to improve yield of biologic drug substance.",
        "priority": "High",
        "status": "Draft Generated",
        "site": "Site B - Mumbai",
        "owner": "A. Sharma",
        "detected_date": _d(4),
        "product_family": "Biologic drug substance",
        "batch_lot": "",
        "regulatory_refs": ["ICH Q8", "21 CFR 314.70"],
    },
    {
        "id": "QR-2026-DEMO-010",
        "type": "nc",
        "sector": "Medical Device",
        "title": "Packaging integrity failure on cardiac devices",
        "description": "Seal integrity testing failed on sterile packaging for cardiac devices (2.5 percent failure rate in-process).",
        "priority": "Critical",
        "status": "Draft Generated",
        "site": "Site A - Chennai",
        "owner": "R. Patel",
        "detected_date": _d(2),
        "product_family": "Cardiac devices",
        "batch_lot": "MD-DEMO-PKG-4",
        "regulatory_refs": ["ISO 11607", "ASTM F2097"],
    },
]


DEMO_CAPAS: list[dict] = [
    {
        "capa_id": "CAPA-2026-DEMO-001",
        "record_id": "QR-2026-DEMO-001",
        "status": "Draft Generated",
        "approved": False,
        "root_cause": "Autoclave load pattern deviated from validated configuration, causing insufficient steam penetration on affected samples.",
        "immediate_action": "Quarantine lot MD-DEMO-A; halt release of any product from the same sterilisation cycle.",
        "corrective_action": "Requalify autoclave load pattern; re-train operators on load configuration SOP.",
        "preventive_action": "Introduce automated load-pattern verification via barcode-checked racks; add periodic requalification.",
        "proposed_owner": "R. Patel",
        "effectiveness_check": "Zero sterility failures across next 20 lots and successful requalification report.",
        "estimated_closure_days": 90,
        "risk_rating": "Critical",
        "regulatory_refs": ["21 CFR Part 820", "ISO 13485:2016"],
        "created_by_username": "quality",
        "ai_provider": "mock",
        "ai_model": "demo-seed",
        "rca_quality_score": 0.82,
    },
    {
        "capa_id": "CAPA-2026-DEMO-004",
        "record_id": "QR-2026-DEMO-004",
        "status": "Under Review",
        "approved": False,
        "root_cause": "Filter integrity marginal on aseptic filling line; particulate carry-over during a shift change.",
        "immediate_action": "Hold impacted batch; visual inspection of retained samples across last 5 lots.",
        "corrective_action": "Replace filter housings; tighten changeover checklist between shifts.",
        "preventive_action": "Add pre-use post-sterilisation integrity testing; upgrade filter housings on all injectable lines.",
        "proposed_owner": "M. Reddy",
        "effectiveness_check": "Three consecutive campaigns with zero particulate observations in retain samples.",
        "estimated_closure_days": 60,
        "risk_rating": "Critical",
        "regulatory_refs": ["21 CFR 211.192", "USP 788"],
        "created_by_username": "quality",
        "ai_provider": "mock",
        "ai_model": "demo-seed",
        "rca_quality_score": 0.76,
    },
    {
        "capa_id": "CAPA-2026-DEMO-008",
        "record_id": "QR-2026-DEMO-008",
        "status": "Approved",
        "approved": True,
        "approved_by": "admin",
        "approved_at": _utcnow_naive(),
        "root_cause": "Artwork approval workflow allowed a non-current dosage version to be routed to press.",
        "immediate_action": "Recall impacted batch; issue field safety notice through affiliates.",
        "corrective_action": "Update artwork release SOP to require dual e-sign on any dosage-field change.",
        "preventive_action": "Implement automated artwork-diff checker with regulatory dosage lookup.",
        "proposed_owner": "D. Mehta",
        "effectiveness_check": "Six months without recurrence and 100 percent dual-signature adherence.",
        "estimated_closure_days": 45,
        "risk_rating": "High",
        "regulatory_refs": ["21 CFR Part 201", "EU FMD 2011/62"],
        "created_by_username": "admin",
        "ai_provider": "mock",
        "ai_model": "demo-seed",
        "rca_quality_score": 0.88,
    },
]


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

def _seed_records(session) -> int:
    inserted = 0
    for spec in DEMO_RECORDS:
        exists = session.query(QualityRecord).filter_by(id=spec["id"]).first()
        if exists:
            continue
        session.add(QualityRecord(
            **spec,
            source="manual",
            age_days=_age_days(spec["detected_date"]),
        ))
        inserted += 1
    return inserted


def _seed_capas(session) -> int:
    inserted = 0
    for spec in DEMO_CAPAS:
        exists = session.query(CAPARecord).filter_by(capa_id=spec["capa_id"]).first()
        if exists:
            continue
        # Ensure parent record exists (should, given seed order).
        parent = session.query(QualityRecord).filter_by(id=spec["record_id"]).first()
        if not parent:
            log.warning("seed.capa.parent_missing", extra={"capa_id": spec["capa_id"]})
            continue
        session.add(CAPARecord(**spec))
        inserted += 1
    return inserted


def main() -> int:
    init_db()
    session = SessionLocal()
    try:
        r = _seed_records(session)
        c = _seed_capas(session)
        session.commit()
    except Exception:
        session.rollback()
        log.exception("seed.failed")
        return 1
    finally:
        session.close()

    log.info("seed.done", extra={"records_inserted": r, "capas_inserted": c})
    print(f"Seed complete. Records inserted: {r}. CAPAs inserted: {c}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
