# services/capa_service.py
# CAPA generation logic — pure Python, no Flask imports
# Like a @Service class in Spring Boot
# Routes call build_mock_capa() → get back a ready CAPA dict

from typing import Dict

# ─────────────────────────────────────────────────────────────
# CAPA TEMPLATES  —  one per record type
# ─────────────────────────────────────────────────────────────
_TEMPLATES: Dict = {
    "complaint": {
        "rootCause": (
            "Customer complaint analysis and traceability review for {sector} product "
            "identified a process control gap at {site} as the primary contributor. {batch_note}"
        ),
        "immediateAction": (
            "Quarantine affected batch/lot. Issue field safety notice to all distributors. "
            "Initiate formal recall/FSCA assessment per SOP-RC-001. "
            "Notify relevant regulatory bodies within mandatory timelines."
        ),
        "correctiveAction": (
            "Redesign affected process step with enhanced in-process acceptance criteria. "
            "Update supplier qualification requirements and process FMEA. "
            "Revise applicable SOPs and re-train personnel on revised controls."
        ),
        "preventiveAction": (
            "Update FMEA risk scores across all critical process steps. "
            "Implement SPC at identified CTQs. "
            "Add complaint trend review to monthly QMR agenda. "
            "Expand post-market surveillance programme to capture early signals."
        ),
        "proposedOwner": "Senior QA Manager – Complaints",
        "effectivenessCheck": (
            "Zero recurrence of same complaint category for 6 consecutive months "
            "post-implementation; confirmed via monthly complaint trending dashboard."
        ),
        "closureDays": {
            "Critical": 30, "High": 60, "Medium": 90, "Low": 120
        },
    },

    "deviation": {
        "rootCause": (
            "Root cause investigation of {title_lc} reveals inadequate preventive "
            "maintenance scheduling and absence of real-time alert thresholds "
            "as primary contributing factors."
        ),
        "immediateAction": (
            "Suspend affected process and quarantine implicated batches. "
            "Issue deviation report to QA and production management within 24 hours. "
            "Perform immediate equipment inspection and re-calibration where applicable."
        ),
        "correctiveAction": (
            "Revise relevant SOP with tightened intervals and improved control measures. "
            "Implement automated monitoring alerts with documented escalation matrix. "
            "Perform formal re-qualification of affected equipment or process."
        ),
        "preventiveAction": (
            "Integrate predictive maintenance into CMMS. "
            "Establish cross-site deviation trending review during monthly QMR. "
            "Add topic to annual internal audit plan and risk register."
        ),
        "proposedOwner": "QA Engineer + Facilities / Production Manager",
        "effectivenessCheck": (
            "No repeat excursions over 3-month post-implementation monitoring period. "
            "Relevant KPI ≥98% for 2 consecutive quarters."
        ),
        "closureDays": {
            "Critical": 30, "High": 45, "Medium": 60, "Low": 90
        },
    },

    "cc": {
        "rootCause": (
            "Root cause analysis of failed change control ({change_type}) identifies "
            "inadequate pre-implementation risk assessment and insufficient V&V "
            "as the primary failure mode. "
            "Contributing factors include governance gaps at {site}."
        ),
        "immediateAction": (
            "Immediately revert or suspend the failed change. "
            "Quarantine any batches affected. "
            "Notify QA, Regulatory, and Operations. "
            "Issue change failure report within 24 hours."
        ),
        "correctiveAction": (
            "Conduct formal failure mode investigation with multi-disciplinary team. "
            "Redesign the change implementation plan with additional risk assessment "
            "and expanded V&V scope. "
            "Re-submit through formal change control with strengthened technical package."
        ),
        "preventiveAction": (
            "Revise Change Control SOP to mandate pre-implementation risk assessment "
            "checklist and stage-gate sign-offs for all changes above defined risk threshold. "
            "Add change control effectiveness metrics to QMR dashboard."
        ),
        "proposedOwner": "Change Control Board Lead + Quality Director",
        "effectivenessCheck": (
            "No repeat failures in same category for 12 months. "
            "Change control governance KPI ≥95% on-time closure rate for 2 quarters."
        ),
        "closureDays": {
            "Critical": 45, "High": 60, "Medium": 90, "Low": 120
        },
    },

    "nc": {
        "rootCause": (
            "Investigation of {title_lc} points to equipment wear beyond acceptable limits "
            "compounded by insufficient in-process monitoring frequency."
        ),
        "immediateAction": (
            "Segregate and quarantine all nonconforming material. "
            "Halt production at affected station. "
            "Initiate formal disposition review per SOP-NC-003."
        ),
        "correctiveAction": (
            "Replace or recalibrate affected equipment. "
            "Increase in-process check frequency at identified critical parameters. "
            "Validate corrected process before resumption."
        ),
        "preventiveAction": (
            "Revise equipment lifecycle management policy. "
            "Add OOS trend analysis to monthly QMR. "
            "Update PFMEA risk scores."
        ),
        "proposedOwner": "QA Manager + Production Supervisor",
        "effectivenessCheck": (
            "Cpk ≥1.33 sustained over 30 consecutive batches. "
            "Zero OOS recurrence confirmed at 90-day follow-up."
        ),
        "closureDays": {
            "Critical": 20, "High": 30, "Medium": 45, "Low": 60
        },
    },
}

_DEFAULT_REFS = ["21 CFR 820.100", "ISO 13485:2016 §8.5.2"]


# ─────────────────────────────────────────────────────────────
# PUBLIC FUNCTION  —  called by routes/capa.py
# ─────────────────────────────────────────────────────────────
def build_mock_capa(record: Dict) -> Dict:
    """
    Builds a CAPA from templates based on record type.
    Like a factory method in Java.

    Args:
        record: the quality record dict from data/records.py
    Returns:
        Full CAPA dict ready to return as JSON
    """
    rtype = record.get("type", "nc")
    tpl   = _TEMPLATES.get(rtype, _TEMPLATES["nc"])
    prio  = record.get("priority", "Medium")

    # Context variables injected into template strings
    ctx = {
        "site":        record.get("site", "the site"),
        "sector":      record.get("sector", ""),
        "title_lc":    record.get("title", "the issue").lower(),
        "change_type": record.get("changeType", "process change"),
        "batch_note":  (
            f"Batch/lot {record['batchLot']} is the implicated production unit."
            if record.get("batchLot") else ""
        ),
    }

    return {
        "rootCause":            tpl["rootCause"].format(**ctx),
        "immediateAction":      tpl["immediateAction"],
        "correctiveAction":     tpl["correctiveAction"],
        "preventiveAction":     tpl["preventiveAction"],
        "proposedOwner":        tpl["proposedOwner"],
        "effectivenessCheck":   tpl["effectivenessCheck"],
        "estimatedClosureDays": tpl["closureDays"].get(prio, 45),
        "riskRating":           prio,
        "regulatoryRef":        record.get("regulatoryRef") or _DEFAULT_REFS,
    }