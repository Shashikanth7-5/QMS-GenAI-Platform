# services/rca_service.py  (or project root rca_service.py)
# 5-Why + Fishbone + Gate evaluator + Accuracy Assessor
# + AI Improvement Suggestions + 3-Model Proposer
# Model scores: A=70%, B=80%, C=90%

from datetime import datetime
from typing import Dict, List
from data.gate_definitions import GATE_DEFS


# ─────────────────────────────────────────────────────────
# 5-WHY CHAIN BUILDER
# ─────────────────────────────────────────────────────────
def build_five_why(record: Dict) -> Dict:
    rtype = record.get("type", "nc")
    chains = {
        "complaint": [
            {"level": 1, "why": "Why did the customer complaint occur?",
             "because": "The product failed to meet performance specifications during use."},
            {"level": 2, "why": "Why did the product fail to meet specifications?",
             "because": "Manufacturing process produced units outside validated control limits."},
            {"level": 3, "why": "Why were units produced outside control limits?",
             "because": "In-process monitoring frequency was insufficient to detect drift."},
            {"level": 4, "why": "Why was monitoring frequency insufficient?",
             "because": "Process FMEA did not identify this parameter as a CCP."},
            {"level": 5, "why": "Why was the parameter not identified as a CCP?",
             "because": "FMEA was not updated after the Q2 process change.", "is_root": True},
        ],
        "deviation": [
            {"level": 1, "why": "Why did the deviation occur?",
             "because": "Process parameter drifted outside specification."},
            {"level": 2, "why": "Why did the parameter drift outside specification?",
             "because": "Equipment performance degraded below the operational threshold."},
            {"level": 3, "why": "Why did equipment performance degrade?",
             "because": "Preventive maintenance was overdue — PM schedule not adhered to."},
            {"level": 4, "why": "Why was the PM schedule not followed?",
             "because": "CMMS alert was suppressed by operator and not escalated."},
            {"level": 5, "why": "Why was the alert suppressed without escalation?",
             "because": "No defined escalation SOP exists for CMMS alert handling.",
             "is_root": True},
        ],
        "cc": [
            {"level": 1, "why": "Why did the change control fail?",
             "because": "Change did not perform as expected post-implementation."},
            {"level": 2, "why": "Why did it not perform as expected?",
             "because": "Pre-implementation risk assessment did not cover all failure modes."},
            {"level": 3, "why": "Why were failure modes missed?",
             "because": "CCB lacked representation from QC and Regulatory."},
            {"level": 4, "why": "Why was the review team incomplete?",
             "because": "Change was classified as minor, bypassing full CCB review."},
            {"level": 5, "why": "Why was it classified minor incorrectly?",
             "because": "Classification criteria in SOP-CC-001 are ambiguous.",
             "is_root": True},
        ],
    }
    chain = chains.get(rtype, chains["deviation"])
    return {
        "method":            "5-Why",
        "record_id":         record.get("id"),
        "problem_statement": record.get("title", ""),
        "chain":             chain,
        "root_cause":        chain[-1]["because"],
        "generated_at":      datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────
# FISHBONE BUILDER
# ─────────────────────────────────────────────────────────
def build_fishbone(record: Dict) -> Dict:
    rtype = record.get("type", "nc")
    cat_map = {
        "complaint": {
            "Man":         [{"text": "Inadequate operator training",               "primary": True},
                            {"text": "High staff turnover disrupted knowledge",    "primary": False}],
            "Machine":     [{"text": "Calibration drift in torque tool",           "primary": True},
                            {"text": "Vision inspection threshold too low",         "primary": False}],
            "Method":      [{"text": "Acceptance criteria not updated post-change","primary": True},
                            {"text": "FMEA not reviewed after supplier change",    "primary": False}],
            "Material":    [{"text": "Batch-to-batch raw material inconsistency",  "primary": True},
                            {"text": "Incoming material variability",              "primary": False}],
            "Measurement": [{"text": "PMS KPIs not capturing early signals",       "primary": True},
                            {"text": "Trending dashboard lacks threshold alerts",  "primary": False}],
            "Environment": [{"text": "Cleanroom temperature variation",            "primary": False},
                            {"text": "Humidity control failure",                   "primary": False}],
        },
        "deviation": {
            "Man":         [{"text": "Operator did not follow SOP step 7.3",       "primary": False},
                            {"text": "Training records not current",               "primary": False}],
            "Machine":     [{"text": "Preventive maintenance overdue 12 days",     "primary": True},
                            {"text": "No real-time alert for threshold breach",    "primary": True}],
            "Method":      [{"text": "PM SOP lacks escalation criteria",           "primary": True},
                            {"text": "No stage-gate check before batch release",   "primary": False}],
            "Material":    [{"text": "Hold time exceeded validated limits",        "primary": True},
                            {"text": "Buffer pH out of specification",             "primary": False}],
            "Measurement": [{"text": "Monitoring frequency too low for drift",     "primary": True},
                            {"text": "OOS investigation not triggered promptly",   "primary": False}],
            "Environment": [{"text": "HVAC filter PM overdue",                     "primary": True},
                            {"text": "Temperature excursion in storage",           "primary": False}],
        },
        "cc": {
            "Man":         [{"text": "CCB missing QC and Regulatory members",      "primary": True},
                            {"text": "Change owner not trained on risk assessment","primary": False}],
            "Machine":     [{"text": "V&V equipment not recalibrated",             "primary": False},
                            {"text": "Scale-up parameters not re-optimised",       "primary": False}],
            "Method":      [{"text": "SOP-CC-001 classification criteria ambiguous","primary": True},
                            {"text": "No mandatory stage-gate before implementation","primary": True}],
            "Material":    [{"text": "New supplier properties differ from approved","primary": True},
                            {"text": "Equivalence testing scope insufficient",     "primary": False}],
            "Measurement": [{"text": "Effectiveness check criteria not defined",   "primary": True},
                            {"text": "Post-implementation monitoring metrics missing","primary": False}],
            "Environment": [{"text": "CMO facility not equivalent to originator",  "primary": False},
                            {"text": "Regulatory change not in risk assessment",   "primary": False}],
        },
    }
    cats = cat_map.get(rtype, cat_map["deviation"])
    return {
        "method":            "Fishbone",
        "record_id":         record.get("id"),
        "problem_statement": record.get("title", ""),
        "categories":        cats,
        "generated_at":      datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────
# ACCURACY ASSESSOR
# ─────────────────────────────────────────────────────────
_SPECIFIC_KEYWORDS = [
    "sop", "sop-", "process", "equipment", "calibration", "procedure",
    "parameter", "specification", "protocol", "batch", "lot", "fmea",
    "ccp", "validation", "cmms", "pm", "schedule", "threshold",
    "frequency", "21 cfr", "iso", "iec", "ich", "gmp", "gdp",
]
_ACTIONABLE_KEYWORDS = [
    "not updated", "not defined", "missing", "absent", "lack",
    "insufficient", "no defined", "overdue", "not adhered",
    "bypassed", "ambiguous", "suppressed", "not performed",
    "not reviewed", "not identified", "not completed",
]
_COMPLETE_KEYWORDS = [
    "because", "due to", "resulted in", "caused by",
    "contributing", "identified", "confirmed", "analysis",
    "investigation", "review", "assessment",
]


def _score_text(text: str) -> Dict:
    t = text.lower()
    spec_hits  = sum(1 for k in _SPECIFIC_KEYWORDS   if k in t)
    act_hits   = sum(1 for k in _ACTIONABLE_KEYWORDS if k in t)
    comp_hits  = sum(1 for k in _COMPLETE_KEYWORDS   if k in t)
    word_count = len(text.split())

    specificity   = min(100, 40 + (spec_hits * 15))
    actionability = min(100, 35 + (act_hits  * 20))
    completeness  = min(100, 30 + (comp_hits * 15) + min(word_count * 2, 30))
    overall       = round((specificity + actionability + completeness) / 3)

    if overall >= 75:   label, color = "Strong",   "green"
    elif overall >= 55: label, color = "Moderate", "amber"
    else:               label, color = "Weak",     "red"

    feedback = []
    if specificity   < 60: feedback.append("Add specific SOP / process / equipment references")
    if actionability < 60: feedback.append("Clarify what was missing, absent or not performed")
    if completeness  < 60: feedback.append("Expand with more context and detail")
    if not feedback:
        feedback.append("Well-structured — ready for CAPA")

    improvement = _suggest_improvement(text, specificity, actionability, completeness)

    return {
        "specificity":   specificity,
        "actionability": actionability,
        "completeness":  completeness,
        "overall":       overall,
        "label":         label,
        "color":         color,
        "feedback":      feedback,
        "improvement":   improvement,
    }


def _suggest_improvement(text: str, spec: int, act: int, comp: int) -> str:
    suggestions = []
    if spec < 60:
        suggestions.append(
            "Reference the specific SOP number, equipment ID, or process parameter "
            "(e.g. 'SOP-QA-007', 'pH meter Unit-12', 'dissolution parameter Q')."
        )
    if act < 60:
        suggestions.append(
            "State explicitly what was NOT done or was MISSING "
            "(e.g. 'calibration SOP was not followed', 'PM schedule had no escalation pathway')."
        )
    if comp < 60:
        suggestions.append(
            "Add the consequence or evidence "
            "(e.g. 'resulting in batch DS-5503 exceeding bioburden spec of ≤5 CFU/10 mL')."
        )
    if not suggestions:
        return "This statement is strong. No changes needed."
    return " ".join(suggestions)


def assess_five_why(rca_data: Dict) -> Dict:
    chain          = rca_data.get("chain", [])
    assessed_steps = []
    total_score    = 0

    for step in chain:
        score = _score_text(step.get("because", ""))
        assessed_steps.append({**step, "score": score})
        total_score += score["overall"]

    overall = round(total_score / len(chain)) if chain else 0

    if overall >= 75:
        verdict, verdict_color = "Strong RCA",   "green"
        verdict_msg = "Chain is well-structured, specific and actionable. Ready to submit."
    elif overall >= 55:
        verdict, verdict_color = "Moderate RCA", "amber"
        verdict_msg = "Acceptable but some steps need more detail. Review flagged steps."
    else:
        verdict, verdict_color = "Weak RCA",     "red"
        verdict_msg = "Chain lacks specificity. Use AI Improve or edit flagged steps."

    return {
        "method":          "5-Why",
        "overall_score":   overall,
        "verdict":         verdict,
        "verdict_color":   verdict_color,
        "verdict_msg":     verdict_msg,
        "assessed_steps":  assessed_steps,
        "assessed_at":     datetime.now().isoformat(),
        "ready_to_submit": overall >= 55,
        "needs_ai_help":   overall < 55,
    }


def assess_fishbone(rca_data: Dict) -> Dict:
    categories    = rca_data.get("categories", {})
    assessed_cats = {}
    cat_scores    = []

    for cat, causes in categories.items():
        scored_causes = []
        for cause in causes:
            score = _score_text(cause.get("text", ""))
            scored_causes.append({**cause, "score": score})
            if cause.get("primary"):
                cat_scores.append(score["overall"])
        assessed_cats[cat] = scored_causes

    overall = round(sum(cat_scores) / len(cat_scores)) if cat_scores else 0

    if overall >= 75:
        verdict, verdict_color = "Strong RCA",   "green"
        verdict_msg = "Primary causes are specific and actionable. Ready to submit."
    elif overall >= 55:
        verdict, verdict_color = "Moderate RCA", "amber"
        verdict_msg = "Most primary causes are acceptable. Review flagged ones."
    else:
        verdict, verdict_color = "Weak RCA",     "red"
        verdict_msg = "Primary causes lack specificity. Use AI Improve or edit flagged causes."

    return {
        "method":              "Fishbone",
        "overall_score":       overall,
        "verdict":             verdict,
        "verdict_color":       verdict_color,
        "verdict_msg":         verdict_msg,
        "assessed_categories": assessed_cats,
        "assessed_at":         datetime.now().isoformat(),
        "ready_to_submit":     overall >= 55,
        "needs_ai_help":       overall < 55,
    }


# ─────────────────────────────────────────────────────────
# 3-MODEL PROPOSER  —  scores: A=70%, B=80%, C=90%
# ─────────────────────────────────────────────────────────
_MODEL_TEMPLATES = {
    "complaint": {
        "basic": {
            "Man":         [{"text": "Operator training on assembly SOP-MFG-012 was not completed before batch start.", "primary": True},
                            {"text": "High staff turnover in Q3 disrupted knowledge transfer for critical processes.", "primary": False}],
            "Machine":     [{"text": "Torque verification tool (ID: TQ-204) had calibration overdue by 8 days at time of production.", "primary": True},
                            {"text": "Vision inspection camera sensitivity was set below validated threshold per SOP-QC-008.", "primary": False}],
            "Method":      [{"text": "In-process acceptance criteria in SOP-PROD-007 were not updated after Q2 design change.", "primary": True},
                            {"text": "Process FMEA (FM-2024-003) was not reviewed after supplier material substitution in Aug 2024.", "primary": False}],
            "Material":    [{"text": "Batch-to-batch raw material inconsistency from approved supplier — particle size RSD exceeded 3%.", "primary": True},
                            {"text": "Incoming material variability not captured in CoA acceptance criteria.", "primary": False}],
            "Measurement": [{"text": "PMS KPI dashboard lacked complaint trending by product family — early signals were missed.", "primary": True},
                            {"text": "Monthly QMR complaint review did not include statistical threshold alerts.", "primary": False}],
            "Environment": [{"text": "Cleanroom temperature variation outside ±2°C during peak production hours.", "primary": False},
                            {"text": "Humidity control system failure — no backup alert configured.", "primary": False}],
        },
        "standard": {
            "Man":         [{"text": "Operator qualification record (OQR-2024-089) was not signed before batch CMP-0891 was initiated, violating SOP-HR-003 §4.2.", "primary": True},
                            {"text": "Staff turnover rate of 28% in Q3 led to 4 unqualified operators working on critical assembly line without supervision.", "primary": False}],
            "Machine":     [{"text": "Torque verification tool TQ-204 calibration lapsed on 02-Nov-2024 (cert expiry: 01-Nov); 3 batches produced during lapse window.", "primary": True},
                            {"text": "Vision inspection system AVS-3 sensitivity threshold was manually overridden to 0.3% vs validated 0.5% per IQ/OQ protocol VP-2023-12.", "primary": False}],
            "Method":      [{"text": "SOP-PROD-007 Rev.4 acceptance criteria were not updated to reflect design change DCN-2024-017 approved in Q2, creating undocumented process gap.", "primary": True},
                            {"text": "FMEA FM-2024-003 RPN scores for luer lock assembly were not recalculated after supplier material substitution per SOP-RA-002.", "primary": False}],
            "Material":    [{"text": "Raw material batch RM-7712 showed particle size D90 of 128 µm vs specification ≤110 µm — CoA accepted without retest per SOP-QC-015.", "primary": True},
                            {"text": "Incoming material acceptance criteria in SOP-QC-015 do not include particle size distribution testing for this material grade.", "primary": False}],
            "Measurement": [{"text": "PMS dashboard KPI-07 (complaint rate by product family) had 90-day reporting lag, preventing early signal detection per SOP-PMS-004.", "primary": True},
                            {"text": "QMR review agenda (QMR-Q3-2024) did not include complaint trend analysis against statistical control limits.", "primary": False}],
            "Environment": [{"text": "Cleanroom B temperature deviated ±3.2°C from setpoint during peak shift due to HVAC unit HVAC-B2 compressor fault.", "primary": False},
                            {"text": "Cold storage CR-4 alarm threshold was set to +8.5°C vs validated limit of +8.0°C per SOP-FAC-009.", "primary": False}],
        },
        "enhanced": {
            "Man":         [{"text": "Operator qualification record OQR-2024-089 was not completed per SOP-HR-003 §4.2 before batch CMP-0891 initiation on 10-Nov-2024. Root cause confirmed via CCTV audit and training matrix review — operator had not completed Module 3 (luer lock assembly) of QT-2024-007.", "primary": True},
                            {"text": "28% staff turnover in Q3-2024 resulted in 4 operators on critical assembly line without qualification sign-off, violating SOP-HR-003 §3.1 minimum competency requirement. HR escalation not triggered per SOP-HR-005.", "primary": False}],
            "Machine":     [{"text": "Torque verification tool TQ-204 (calibration certificate CAL-2024-0812, expiry 01-Nov-2024) was used for 3 production days (02–04 Nov) beyond expiry. Calibration CMMS alert was acknowledged without action by Line Supervisor — no escalation path defined in SOP-EQ-006 §5.3.", "primary": True},
                            {"text": "Vision inspection system AVS-3 sensitivity threshold was manually overridden from validated 0.5% (IQ/OQ: VP-2023-12) to 0.3% on 08-Nov by maintenance engineer without formal change control per SOP-CC-001 §3.2.", "primary": False}],
            "Method":      [{"text": "SOP-PROD-007 Rev.4 acceptance criteria for luer lock torque (8–12 Nm) were not updated to reflect Design Change Notice DCN-2024-017 (new torque range 10–14 Nm) approved by CCB on 14-Aug-2024. SOP revision workflow (SOP-DC-001) was initiated but not completed due to document owner vacancy.", "primary": True},
                            {"text": "Process FMEA FM-2024-003 RPN scores for luer lock assembly (RPN=168) were not recalculated after supplier material substitution approval (SCN-2024-021) per SOP-RA-002 §4.4 requirement for FMEA review within 30 days of approved material change.", "primary": False}],
            "Material":    [{"text": "Raw material batch RM-7712 (supplier: MedPoly Ltd, PO-2024-0445) showed particle size D90 of 128 µm against specification ≤110 µm per STP-RM-004. CoA accepted by QC without retest because SOP-QC-015 §3.1 only mandates retest for D50 — gap in incoming acceptance criteria identified during investigation.", "primary": True},
                            {"text": "SOP-QC-015 incoming material acceptance criteria for polymer grade MG-B do not include D90 particle size testing — specification gap not identified during last SOP review (Rev.3, Jan 2024).", "primary": False}],
            "Measurement": [{"text": "PMS KPI dashboard (SOP-PMS-004) KPI-07 complaint rate by product family had 90-day reporting lag due to manual data extraction. Three complaint signals (CMP-0871, CMP-0878, CMP-0887) from same product family in 60-day window were not escalated because automated threshold alert was not configured in the QMR template.", "primary": True},
                            {"text": "Q3-2024 QMR review complaint trend analysis section was marked N/A by QA Manager due to absence of statistical baseline data — baseline not established per SOP-PMS-004 §6.2.", "primary": False}],
            "Environment": [{"text": "Cleanroom B HVAC unit HVAC-B2 compressor fault on 08-Nov caused temperature deviation ±3.2°C from 22°C setpoint during 06:00–14:00 shift. PM was overdue by 18 days (last PM: 21-Sep, scheduled: 20-Oct per CMMS-2024-PM-0441). No CAPA raised for PM overdue — deviation classified minor per SOP-ENV-003 §4.1 without batch impact assessment.", "primary": False},
                            {"text": "Cold storage CR-4 temperature alarm set to +8.5°C threshold instead of +8.0°C due to data entry error during alarm system reconfiguration on 15-Oct-2024. Error not detected during weekly alarm verification check per SOP-FAC-009 §7.2.", "primary": False}],
        },
    },
    "deviation": {
        "basic": {
            "Man":         [{"text": "Operator skipped SOP step 7.3 (equipment pre-use check) without supervisory sign-off.", "primary": False},
                            {"text": "Training records for Line 3 operators were not current — 2 of 5 operators overdue for annual retraining.", "primary": False}],
            "Machine":     [{"text": "Preventive maintenance for pH meter Unit-12 was overdue by 12 days per CMMS schedule.", "primary": True},
                            {"text": "No real-time alert was configured for pH threshold breach.", "primary": True}],
            "Method":      [{"text": "PM SOP-EQ-006 lacked escalation criteria for overdue maintenance — no supervisor notification trigger defined.", "primary": True},
                            {"text": "No stage-gate check was required before batch release when critical equipment PM was overdue.", "primary": False}],
            "Material":    [{"text": "Drug substance hold time exceeded validated limit of 48h — actual hold was 72h.", "primary": True},
                            {"text": "Buffer pH was out of specification due to incorrect preparation sequence.", "primary": False}],
            "Measurement": [{"text": "In-process pH monitoring frequency of every 4 hours was insufficient to detect drift.", "primary": True},
                            {"text": "OOS investigation procedure was not triggered promptly — 6-hour delay.", "primary": False}],
            "Environment": [{"text": "HVAC filter PM overdue by 14 days — particulate count exceeded action limit.", "primary": True},
                            {"text": "Temperature excursion in cold storage unit CR-4.", "primary": False}],
        },
        "standard": {
            "Man":         [{"text": "Operator skipped SOP-MFG-044 step 7.3 equipment pre-use pH check — training records show procedure not covered in last requalification (OQR-2024-045, dated 03-Aug-2024).", "primary": False},
                            {"text": "2 of 5 Line 3 operators were overdue for annual GMP retraining per SOP-HR-003 §5.1 — no production restriction applied while overdue.", "primary": False}],
            "Machine":     [{"text": "pH meter Unit-12 preventive maintenance was overdue by 12 days per CMMS-2024-PM-0312 schedule. CMMS alert acknowledged by operator on Day 8 without escalation to QA per SOP-EQ-006 §4.3.", "primary": True},
                            {"text": "No automated real-time pH threshold alert was configured in the process control system PCS-MFG-003 — operator relied solely on manual 4-hourly readings.", "primary": True}],
            "Method":      [{"text": "PM SOP-EQ-006 Rev.3 did not define escalation criteria for overdue PM beyond 7 days — gap identified during deviation investigation.", "primary": True},
                            {"text": "Batch release SOP-REL-002 did not require confirmation that all critical equipment PMs were current before batch disposition.", "primary": False}],
            "Material":    [{"text": "Drug substance DS-5503 hold time of 72h exceeded validated limit of 48h per SOP-MFG-019 §6.2. Extended hold required due to downstream GF-12 equipment unavailability — no contingency procedure defined.", "primary": True},
                            {"text": "Buffer preparation SOP-MFG-044 step 3.2 was not followed — ingredient addition sequence was reversed, causing pH of 6.2 vs specification 7.0–7.4.", "primary": False}],
            "Measurement": [{"text": "In-process pH monitoring performed every 4 hours per SOP-MFG-019 §8.1 was insufficient — process validation PV-2022-003 showed pH drift can occur within 2 hours under elevated temperature conditions.", "primary": True},
                            {"text": "OOS investigation procedure SOP-QC-012 §3.1 requires initiation within 1 hour of OOS result — 6-hour delay observed, attributed to shift changeover without formal handover.", "primary": False}],
            "Environment": [{"text": "HVAC filter PM in Cleanroom B overdue by 14 days (last service: 08-Sep, due: 08-Oct per CMMS). ISO 7 particulate count exceeded action limit (≥3,520 particles/m³ ≥0.5µm) on 22-Oct.", "primary": True},
                            {"text": "Cold storage unit CR-4 temperature alarm threshold set to -18°C vs validated lower limit of -20°C — configuration error introduced during HVAC recertification in Sep 2024.", "primary": False}],
        },
        "enhanced": {
            "Man":         [{"text": "Operator (ID: OP-2024-0312) skipped SOP-MFG-044 step 7.3 equipment pre-use pH verification check. Training record OQR-2024-045 (requalification date: 03-Aug-2024) confirms step 7.3 was included in training — deliberate deviation. Supervisor sign-off waived per informal practice — not authorised by SOP-MFG-044 §2.4.", "primary": False},
                            {"text": "2 of 5 Line 3 operators (OP-0298, OP-0312) overdue for annual GMP retraining per SOP-HR-003 §5.1 by 47 and 31 days respectively. Production restriction procedure SOP-HR-003 §5.3 (suspend from critical operations until requalified) was not applied — QA oversight gap confirmed in deviation investigation.", "primary": False}],
            "Machine":     [{"text": "pH meter Unit-12 (asset tag EQ-2024-PM-0312, calibration certificate PM-CAL-2024-0887 valid to 10-Oct-2024) was used 12 days beyond PM due date. CMMS-generated PM overdue alert (ref: CMMS-2024-PM-0312) was acknowledged on 18-Oct by Line Supervisor without escalation to QA or restriction of equipment use — SOP-EQ-006 §4.3 requires QA notification within 24h of PM overdue for critical equipment. No escalation path defined for Line Supervisor acknowledgement.", "primary": True},
                            {"text": "Process control system PCS-MFG-003 pH threshold alert (action limit: 6.8 pH units) was not configured for Line 3 bioreactor circuit — configuration oversight identified during CAPA investigation. Alert had been active on Lines 1 and 2 since PCS upgrade in Jan 2024 (ECN-2024-001) but Line 3 upgrade was deferred due to maintenance scheduling conflict (ref: CMMS work order WO-2024-0145).", "primary": True}],
            "Method":      [{"text": "PM SOP-EQ-006 Rev.3 (effective 15-Jan-2024) §4.3 defines notification of QA within 24h of PM overdue for GMP-critical equipment but does not define action for continued equipment use beyond 7 days overdue — gap identified during this investigation. Previous version Rev.2 required QA hold after 5 days overdue (SOP-EQ-006 Rev.2 §4.2) — requirement was removed during Rev.3 update without formal risk assessment per SOP-DC-001 §3.4.", "primary": True},
                            {"text": "Batch release SOP-REL-002 Rev.5 §4.1 final disposition checklist does not include verification that all critical equipment PMs are current at time of batch release — gap identified during investigation. Equipment status is available in CMMS but is not referenced in the release checklist.", "primary": False}],
            "Material":    [{"text": "Drug substance DS-5503 (batch DS-5503-2024-001, manufactured 22-Oct-2024) hold time was extended to 72h against validated limit of 48h per SOP-MFG-019 §6.2 and process validation report PV-2022-003. Extension was required due to GF-12 granulation equipment scheduled PM (WO-2024-0501) which overran by 26h. No formal hold time extension procedure exists in SOP-MFG-019 — contingency management procedure SOP-MFG-030 does not cover drug substance hold time exceedances.", "primary": True},
                            {"text": "Buffer solution BSS-04 was prepared with ingredient addition sequence reversed (KH2PO4 added before Na2HPO4 instead of after, as specified in SOP-MFG-044 step 3.2) resulting in pH 6.2 vs specification 7.0–7.4. Operator confirmed awareness of correct sequence — deviation attributed to production pressure during shift end. No independent verification step required for buffer preparation per SOP-MFG-044.", "primary": False}],
            "Measurement": [{"text": "In-process pH monitoring performed every 4 hours per SOP-MFG-019 §8.1 table 3. Process validation report PV-2022-003 section 4.2 documents that pH drift under elevated temperature conditions (>22°C) can reach action limit within 90 minutes — 4-hour interval is insufficient for the observed temperature profile on 22-Oct (max 24.1°C at 14:30). Monitoring frequency was not updated following PV report findings — gap in validation lifecycle procedure SOP-VAL-001 §5.3.", "primary": True},
                            {"text": "OOS investigation SOP-QC-012 §3.1 requires initiation within 1 hour of confirmed OOS result. pH OOS confirmed at 10:15 — investigation not initiated until 16:45 (6h 30min delay). Delay attributed to shift changeover at 14:00 without formal OOS status communication per SOP-QC-012 §3.2 handover requirement.", "primary": False}],
            "Environment": [{"text": "Cleanroom B HVAC filter PM overdue by 14 days (scheduled 08-Oct per CMMS-2024-PM-0441, last service 08-Sep-2024). ISO 7 particle count at monitoring point MP-B3 exceeded action limit (≥3,520 particles/m³ for ≥0.5µm particles per ISO 14644-1) on 22-Oct at 09:00 monitoring. Cleanroom continued in use for 6h after exceedance before HVAC PM was initiated — SOP-ENV-003 §4.1 classifies single-point exceedances as minor deviations not requiring immediate production hold, which is inconsistent with ISO 14644-2 requirement for investigation and corrective action.", "primary": True},
                            {"text": "Cold storage unit CR-4 (validated range -20°C to -25°C per qualification report QR-2021-CR4) temperature alarm set to -18°C threshold at time of exceedance. Validated early-warning alarm threshold per SOP-FAC-009 §7.1 is -19°C. Configuration error introduced during HVAC recertification work on 15-Sep-2024 (work order WO-2024-0398) — not detected during weekly alarm verification (last check 15-Oct-2024) because SOP-FAC-009 §7.2 alarm verification procedure checks activation but not set-point accuracy.", "primary": False}],
        },
    },
}

# Default cc to deviation template
_MODEL_TEMPLATES["cc"] = _MODEL_TEMPLATES["deviation"]


def propose_three_models(record: Dict, method: str) -> Dict:
    """
    Returns three AI-proposed RCA models:
      Model A — Basic      (~70% target)
      Model B — Intermediate (~80% target)
      Model C — Advanced   (~90% target)
    """
    rtype     = record.get("type", "complaint")
    templates = _MODEL_TEMPLATES.get(rtype, _MODEL_TEMPLATES["complaint"])

    model_defs = [
        ("basic",    "Model A — Basic",        70, "🔵",
         "Adds specific SOP numbers and equipment IDs to strengthen specificity.",
         "70% target — Foundational"),
        ("standard", "Model B — Intermediate", 80, "🟡",
         "Adds process parameter values, batch refs, regulatory links and operator IDs.",
         "80% target — Recommended"),
        ("enhanced", "Model C — Advanced",     90, "🟢",
         "Full audit trail — all evidence, CAPA refs, regulatory citations, quantified impact.",
         "90% target — Regulatory grade"),
    ]

    models = []
    for model_key, name, target, icon, desc, badge in model_defs:
        categories = templates.get(model_key, templates["basic"])

        # Compute actual estimated score from model text quality
        primary_scores = [
            _score_text(c["text"])["overall"]
            for causes in categories.values()
            for c in causes if c.get("primary")
        ]
        est_score = round(sum(primary_scores) / len(primary_scores)) if primary_scores else target

        # Build a 5-Why chain from the model categories (for 5-Why mode)
        chain = _build_chain_from_categories(categories, record)

        models.append({
            "id":              model_key,
            "name":            name,
            "icon":            icon,
            "description":     desc,
            "badge":           badge,
            "target_score":    target,
            "estimated_score": est_score,
            "categories":      categories,   # for fishbone
            "chain":           chain,         # for 5-why
        })

    return {
        "models":       models,
        "record_id":    record.get("id"),
        "method":       method,
        "generated_at": datetime.now().isoformat(),
    }


def _build_chain_from_categories(categories: Dict, record: Dict) -> List[Dict]:
    """Build an improved 5-Why chain from fishbone categories."""
    # Pick the primary causes across categories to form a logical chain
    all_primaries = [
        (cat, c["text"])
        for cat, causes in categories.items()
        for c in causes if c.get("primary")
    ]
    # Use up to 5 to form a 5-Why chain
    chain = []
    why_templates = [
        "Why did the quality event occur?",
        "Why did this cause arise?",
        "Why was this not prevented?",
        "Why was the control missing?",
        "Why was the root issue not addressed earlier?",
    ]
    for i, (cat, text) in enumerate(all_primaries[:5]):
        chain.append({
            "level":   i + 1,
            "why":     why_templates[i],
            "because": text,
            "is_root": i == min(len(all_primaries) - 1, 4),
        })
    # Fallback if no primaries
    if not chain:
        chain = build_five_why(record).get("chain", [])
    return chain


# ─────────────────────────────────────────────────────────
# GATE EVALUATOR
# ─────────────────────────────────────────────────────────
def evaluate_gates(source: str, answers: Dict) -> Dict:
    gates     = GATE_DEFS.get(source, [])
    prio      = answers.get("priority", "Medium")
    results   = []
    triggered = None

    for gate in gates:
        gid   = gate["id"]
        value = answers.get(gid, False)
        if gid == "priority_critical_high":
            value = prio in ("Critical", "High")
        results.append({**gate, "answer": bool(value)})
        if value and not triggered:
            triggered = gate

    if triggered:
        return {
            "capa_triggered": True,
            "triggered_gate": triggered["gate"],
            "gate_label":     triggered["label"],
            "mandatory":      triggered["mandatory"],
            "recommendation": "Initiate CAPA immediately. Assign QA owner and set closure date.",
            "gate_results":   results,
        }
    return {
        "capa_triggered": False,
        "triggered_gate": None,
        "gate_label":     "No gate triggered",
        "mandatory":      False,
        "recommendation": "No CAPA required. Log and monitor via PMS. Re-evaluate at QMR.",
        "gate_results":   results,
    }