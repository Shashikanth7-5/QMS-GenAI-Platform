# tests/test_pdf.py
import pytest
from services.pdf_service import build_capa_pdf


SAMPLE = {
    "capaId": "CAPA-TEST-PDF-001",
    "sourceRecordId": "QR-2024-001",
    "status": "Under Review",
    "riskRating": "High",
    "capaOwner": "Senior QA Manager",
    "estimatedClosureDays": 45,
    "regulatoryRef": ["21 CFR Part 820", "ISO 13485"],
    "rootCause": "Process gap in SOP-EQ-006 sterilisation cycle validation",
    "immediateAction": "Quarantine affected lot",
    "correctiveAction": "Revise SOP and retrain",
    "preventiveAction": "Quarterly audit",
    "effectivenessCheck": "Zero recurrence over 6 months",
    "createdAt": "2026-06-11T11:37:44",
}


def test_build_capa_pdf_returns_valid_pdf():
    """PDF bytes start with the PDF magic header and are non-trivial in size."""
    pdf = build_capa_pdf(SAMPLE)
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_build_capa_pdf_handles_missing_fields():
    """Rendering must not crash on a sparse CAPA dict."""
    pdf = build_capa_pdf({"capaId": "CAPA-TEST-PDF-002"})
    assert pdf[:4] == b"%PDF"


def test_build_capa_pdf_with_similar():
    """Optional RAG 'similar' section renders without error."""
    similar = [{"similarity": 0.9, "title": "EO sterilisation abort", "capaId": "CAPA-2026-1234"}]
    pdf = build_capa_pdf(SAMPLE, similar=similar)
    assert pdf[:4] == b"%PDF"


@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        c.post("/login", data={"username": "admin", "password": "admin"},
               follow_redirects=True)
        yield c


def test_export_missing_capa_returns_404(client):
    r = client.get("/api/capa/CAPA-DOES-NOT-EXIST/export")
    assert r.status_code == 404
