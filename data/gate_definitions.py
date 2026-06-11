# data/gate_definitions.py
# Decision tree gate configs for all 3 source types
# Edit labels here without touching any service logic

GATE_DEFS = {
    "complaint": [
        {"id": "adverse_event",          "gate": 1, "label": "Adverse event or patient harm involved?",       "mandatory": True},
        {"id": "priority_critical_high", "gate": 2, "label": "Priority / risk rating Critical or High?",       "mandatory": True},
        {"id": "recurring",              "gate": 3, "label": "Same complaint type recurring (≥3 in 90 days)?", "mandatory": True},
        {"id": "regulatory_reportable",  "gate": 4, "label": "Regulatory reportable (MDR / CDSCO / EMA)?",     "mandatory": True},
        {"id": "systemic_root_cause",    "gate": 5, "label": "Root cause systemic or process-related?",        "mandatory": False},
        {"id": "qa_recommendation",      "gate": 6, "label": "QA discretionary review recommends CAPA?",       "mandatory": False},
    ],
    "deviation": [
        {"id": "batch_patient_impact",   "gate": 1, "label": "Batch released or patient impact possible?",     "mandatory": True},
        {"id": "cqa_breach",             "gate": 2, "label": "Critical quality attribute or CCP out of spec?", "mandatory": True},
        {"id": "validated_process",      "gate": 3, "label": "Affects validated sterilisation / cleanroom?",   "mandatory": True},
        {"id": "recurring",              "gate": 4, "label": "Same deviation category occurred before?",       "mandatory": True},
        {"id": "equipment_failure",      "gate": 5, "label": "Equipment, utility or HVAC primary failure?",    "mandatory": False},
        {"id": "gxp_gap",                "gate": 6, "label": "GxP documentation integrity gap identified?",    "mandatory": True},
    ],
    "cc": [
        {"id": "safety_reg_impact",      "gate": 1, "label": "Patient safety or regulatory submission impact?","mandatory": True},
        {"id": "vv_failure",             "gate": 2, "label": "Verification / validation or study failed?",     "mandatory": True},
        {"id": "unauthorized_change",    "gate": 3, "label": "Change implemented without QA approval?",        "mandatory": True},
        {"id": "cqa_affected",           "gate": 4, "label": "Product CQA or process parameter breached?",     "mandatory": True},
        {"id": "supplier_failure",       "gate": 5, "label": "Supplier, site transfer or CMO batch failed?",   "mandatory": False},
        {"id": "repeat_failure",         "gate": 6, "label": "Same change type failed within 12 months?",      "mandatory": True},
    ],
}