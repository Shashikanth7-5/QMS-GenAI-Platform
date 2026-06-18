# tests/test_rag.py
import pytest
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.vector_store import (
    embed_capa, find_similar, collection_stats, _capa_to_text
)


# ── Vector store unit tests ───────────────────────────────
def test_collection_loads():
    """Vector store initialises and reports a count."""
    stats = collection_stats()
    assert "embedded_capas" in stats
    assert isinstance(stats["embedded_capas"], int)


def test_embed_and_find_similar():
    """A CAPA we embed can be retrieved as similar to a matching query."""
    capa = {
        "capaId": "CAPA-TEST-RAG-001",
        "sourceRecordId": "TEST-REC-001",
        "sourceRecordType": "deviation",
        "sector": "Medical Device",
        "sourceRecordTitle": "Autoclave temperature excursion during sterilisation",
        "rootCause": "Temperature probe SOP-EQ-014 out of calibration",
        "correctiveAction": "Recalibrate probe",
        "preventiveAction": "Quarterly calibration schedule",
        "riskRating": "High",
    }
    assert embed_capa(capa) is True

    results = find_similar({
        "type": "deviation",
        "sector": "Medical Device",
        "title": "Autoclave temperature excursion during sterilisation",
        "description": "sterilisation temperature out of range",
    }, top_k=3)

    assert isinstance(results, list)
    assert len(results) >= 1
    ids = [r["capaId"] for r in results]
    assert "CAPA-TEST-RAG-001" in ids
    # similarity scores are within range
    for r in results:
        assert 0.0 <= r["similarity"] <= 1.0


def test_capa_to_text_includes_fields():
    """Embedded text carries the distinguishing fields."""
    text = _capa_to_text({
        "sourceRecordType": "complaint",
        "sector": "Pharma",
        "sourceRecordTitle": "Tablet dissolution failure",
        "rootCause": "Granulation moisture too high",
    })
    assert "complaint" in text
    assert "Tablet dissolution failure" in text
    assert "Granulation" in text


# ── Endpoint test (logged-in) ─────────────────────────────
@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        c.post("/login", data={"username": "admin", "password": "admin"},
               follow_redirects=True)
        yield c


def test_rag_similar_endpoint(client):
    """The /api/rag/similar endpoint returns similar CAPAs when logged in."""
    r = client.post("/api/rag/similar", json={
        "record": {
            "type": "deviation",
            "sector": "Medical Device",
            "title": "EO sterilisation cycle failure",
            "description": "cycle parameters not met",
        },
        "top_k": 3,
    })
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "similar" in data
    assert "total_embedded" in data
    assert isinstance(data["similar"], list)


def test_rag_similar_missing_record(client):
    """Missing record returns 400."""
    r = client.post("/api/rag/similar", json={})
    assert r.status_code == 400