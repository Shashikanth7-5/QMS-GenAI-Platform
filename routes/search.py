# routes/search.py
# GET  /search           → search page
# GET  /api/search?q=   → role-filtered search results

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from data.records import search_records, get_all_capas, get_capas_by_owner

search_bp = Blueprint("search", __name__)


@search_bp.route("/search")
@login_required
def page_search():
    return render_template("search/index.html")


@search_bp.route("/api/search", methods=["GET"])
@login_required
def api_search():
    q       = request.args.get("q","").strip()
    rtype   = request.args.get("type","")   # records | capas | all
    if not q:
        return jsonify({"records":[],"capas":[],"total":0,"query":""})

    sees_all = current_user.sees_all_records()

    # Search quality records
    records = search_records(
        query    = q,
        username = current_user.username,
        sees_all = sees_all,
    )

    # Search CAPAs
    all_capas = get_all_capas() if sees_all else get_capas_by_owner(current_user.username)
    q_lower   = q.lower()
    capas = [
        c for c in all_capas
        if q_lower in c.get("capaId","").lower()
        or q_lower in c.get("sourceRecordId","").lower()
        or q_lower in c.get("sourceRecordTitle","").lower()
    ]

    return jsonify({
        "records": records[:20],
        "capas":   capas[:20],
        "total":   len(records) + len(capas),
        "query":   q,
        "sees_all": sees_all,
    })
