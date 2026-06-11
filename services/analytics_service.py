# services/analytics_service.py

from collections import Counter
from typing import Dict, List
from data.records import get_all_records


def _records() -> List[Dict]:
    return get_all_records()


def priority_distribution() -> Dict:
    recs   = _records()
    counts = Counter(r.get("priority", "Unknown") for r in recs)
    order  = ["Critical", "High", "Medium", "Low"]
    colors = {
        "Critical": "#c0392b",
        "High":     "#b45309",
        "Medium":   "#1756b8",
        "Low":      "#1e6b3a",
    }
    return {
        "labels": order,
        "values": [counts.get(p, 0) for p in order],
        "colors": [colors[p] for p in order],
        "total":  len(recs),
    }


def status_pipeline() -> Dict:
    recs   = _records()
    stages = ["Draft Generated", "Under Review", "Pending Approval", "Approved"]
    counts = Counter(r.get("status", "") for r in recs)
    colors = {
        "Draft Generated":  "#5b4dc4",
        "Under Review":     "#b45309",
        "Pending Approval": "#1756b8",
        "Approved":         "#1e6b3a",
    }
    return {
        "labels": stages,
        "values": [counts.get(s, 0) for s in stages],
        "colors": [colors[s] for s in stages],
    }


def type_breakdown() -> Dict:
    recs   = _records()
    counts = Counter(r.get("type", "other") for r in recs)
    types  = ["complaint", "deviation", "cc", "nc", "audit"]
    labels = {
        "complaint": "Complaints",
        "deviation": "Deviations",
        "cc":        "Change Control",
        "nc":        "Non-Conformances",
        "audit":     "Audit Findings",
    }
    colors = {
        "complaint": "#1756b8",
        "deviation": "#b45309",
        "cc":        "#5b4dc4",
        "nc":        "#c0392b",
        "audit":     "#1e6b3a",
    }
    active = [t for t in types if counts.get(t, 0) > 0]
    return {
        "labels": [labels[t] for t in active],
        "values": [counts[t] for t in active],
        "colors": [colors[t] for t in active],
        "total":  len(recs),
    }


def sector_split() -> Dict:
    recs    = _records()
    counts  = Counter(r.get("sector", "Other") for r in recs)
    sectors = sorted(counts.keys())
    colors  = {
        "Medical Device": "#1756b8",
        "BioPharma":      "#1e6b3a",
        "Other":          "#7a839e",
    }
    return {
        "labels": sectors,
        "values": [counts[s] for s in sectors],
        "colors": [colors.get(s, "#999") for s in sectors],
    }


def site_workload() -> Dict:
    recs   = _records()
    open_r = [r for r in recs if r.get("status") != "Approved"]
    counts = Counter(r.get("site", "Unknown") for r in open_r)
    top    = counts.most_common(8)
    return {
        "labels": [s for s, _ in top],
        "values": [v for _, v in top],
        "colors": ["#1756b8"] * len(top),
    }


def age_distribution() -> Dict:
    recs    = _records()
    buckets = {"0-7d": 0, "8-14d": 0, "15-30d": 0, "30d+": 0}
    for r in recs:
        age = r.get("age", 0) or 0
        if age <= 7:
            buckets["0-7d"]   += 1
        elif age <= 14:
            buckets["8-14d"]  += 1
        elif age <= 30:
            buckets["15-30d"] += 1
        else:
            buckets["30d+"]   += 1
    return {
        "labels": list(buckets.keys()),
        "values": list(buckets.values()),
        "colors": ["#1e6b3a", "#b45309", "#c0392b", "#7a0000"],
    }