# services/guardrails.py
# Validates CAPA output before saving — no AI needed
# Called by routes/capa.py api_save() before save_capa()

import re
from typing import Dict, List, Tuple

VALID_REGULATORY_REFS = [
    "21 CFR", "ISO 13485", "EU MDR", "ICH", "GMP", "GDP",
    "IEC 62304", "MDR 2017/745", "CDSCO", "21 CFR 820",
    "21 CFR 211", "21 CFR 314", "ICH Q10", "ICH Q8",
]

VAGUE_ROOT_CAUSE_PHRASES = [
    "human error", "operator error", "lack of training",
    "poor communication", "insufficient oversight",
    "inadequate process", "system failure",
]

CAPA_REQUIRED_RULES = [
    {
        "field": "rootCause",
        "label": "Root cause statement",
        "basis": ["21 CFR 820.100(a)(2)", "ISO 13485:2016 8.5.2"],
        "message": "A documented root cause is required before CAPA can enter review.",
    },
    {
        "field": "immediateAction",
        "label": "Immediate containment/action",
        "basis": ["21 CFR 820.100(a)(3)", "EU MDR 2017/745 Article 10(9)"],
        "message": "Containment or immediate correction must be captured for affected product/process control.",
    },
    {
        "field": "correctiveAction",
        "label": "Corrective action",
        "basis": ["21 CFR 820.100(a)(3)", "ISO 13485:2016 8.5.2"],
        "message": "Corrective action is required to address the confirmed cause and prevent recurrence.",
    },
    {
        "field": "preventiveAction",
        "label": "Preventive action",
        "basis": ["21 CFR 820.100(a)", "ISO 13485:2016 8.5.3"],
        "message": "Preventive action is required to control similar or potential issues.",
    },
    {
        "field": "capaOwner",
        "label": "CAPA owner",
        "basis": ["21 CFR 820.20(b)(1)", "ISO 13485:2016 5.5.1"],
        "message": "A responsible role/owner is required for accountability.",
    },
    {
        "field": "effectivenessCheck",
        "label": "Effectiveness check",
        "basis": ["21 CFR 820.100(a)(4)", "ISO 13485:2016 8.5.2"],
        "message": "Effectiveness verification is required to confirm actions worked.",
    },
    {
        "field": "riskRating",
        "label": "Risk rating",
        "basis": ["ISO 14971", "EU MDR 2017/745 Annex I"],
        "message": "Risk rating is required to justify priority and closure expectations.",
    },
]


def regulatory_basis_for_record(capa: Dict) -> List[str]:
    refs = list(capa.get("regulatoryRef") or [])
    sector = (capa.get("sector") or "").lower()
    record_type = (capa.get("sourceRecordType") or "").lower()
    if not refs:
        refs.extend(["21 CFR 820.100", "ISO 13485:2016 8.5.2"])
    if "medical" in sector or "complaint" in record_type:
        refs.extend(["21 CFR 820.198", "EU MDR 2017/745 Article 87"])
    if "bio" in sector or "deviation" in record_type:
        refs.extend(["21 CFR 211.192", "EU GMP Chapter 1"])
    return list(dict.fromkeys(refs))


def required_capa_errors(capa: Dict) -> List[Dict]:
    errors = []
    for rule in CAPA_REQUIRED_RULES:
        value = capa.get(rule["field"])
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(rule)
    if not capa.get("regulatoryRef"):
        errors.append({
            "field": "regulatoryRef",
            "label": "Regulatory references",
            "basis": ["21 CFR 820.100", "ISO 13485:2016 8.5.2", "EU MDR 2017/745"],
            "message": "At least one regulatory reference is required so the CAPA has a traceable basis.",
        })
    return errors


def validate_capa_detailed(capa: Dict) -> Dict:
    errors = required_capa_errors(capa)
    _, warnings = validate_capa(capa)
    return {
        "valid": not errors and not warnings,
        "can_save": not errors,
        "errors": errors,
        "warnings": warnings,
        "basis": regulatory_basis_for_record(capa),
    }


def validate_capa(capa: Dict) -> Tuple[bool, List[str]]:
    """
    Returns (is_valid, list_of_warnings).
    Warnings don't block save — they are shown to the user.
    """
    warnings = []

    # 1. Root cause specificity check
    root_cause = capa.get("rootCause", "").lower()
    for phrase in VAGUE_ROOT_CAUSE_PHRASES:
        if phrase in root_cause and len(root_cause) < 100:
            warnings.append(
                f"Root cause appears vague ('{phrase}' detected). "
                f"Cite a specific SOP number, equipment ID, or process step."
            )
            break

    # 2. Regulatory reference check
    reg_refs = capa.get("regulatoryRef", [])
    if not reg_refs:
        warnings.append(
            "No regulatory references provided. "
            "Add at least one (e.g. 21 CFR 820.100, ISO 13485:2016 §8.5.2)."
        )
    else:
        valid = any(
            any(ref_pattern.lower() in r.lower() for ref_pattern in VALID_REGULATORY_REFS)
            for r in reg_refs
        )
        if not valid:
            warnings.append(
                "Regulatory references do not match known standards. "
                "Verify against 21 CFR, ISO 13485, EU MDR, or ICH guidelines."
            )

    # 3. Closure days range check
    closure_days = int(capa.get("estimatedClosureDays", 0))
    risk = capa.get("riskRating", "Medium")
    limits = {"Critical": (1, 30), "High": (1, 60), "Medium": (1, 90), "Low": (1, 120)}
    lo, hi = limits.get(risk, (1, 120))
    if not (lo <= closure_days <= hi):
        warnings.append(
            f"Estimated closure of {closure_days} days is outside the "
            f"expected range for {risk} risk ({lo}–{hi} days)."
        )

    # 4. Effectiveness check must be measurable
    eff = capa.get("effectivenessCheck", "")
    measurable_keywords = [
        "%", "days", "months", "quarters", "recurrence",
        "rate", "zero", "audit", "review", "KPI"
    ]
    if eff and not any(kw.lower() in eff.lower() for kw in measurable_keywords):
        warnings.append(
            "Effectiveness check does not appear measurable. "
            "Include a metric, timeframe, or KPI (e.g. 'zero recurrence for 6 months')."
        )

    # 5. Proposed owner must be a role, not a name
    owner = capa.get("capaOwner", "")
    if owner and re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+$', owner.strip()):
        warnings.append(
            f"CAPA owner '{owner}' appears to be a personal name. "
            f"Use a job title instead (e.g. 'Senior QA Manager')."
        )

    return len(warnings) == 0, warnings
