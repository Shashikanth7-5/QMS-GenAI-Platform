# tests/conftest.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app


def _test_app():
    a = create_app()
    a.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False,
                     "SECRET_KEY": "test-secret"})
    return a


@pytest.fixture(scope="session")
def app():
    yield _test_app()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client():
    c = _test_app().test_client()
    c.post("/login", data={"username": "admin", "password": "admin"})
    yield c
    c.get("/logout")


@pytest.fixture
def quality_client():
    c = _test_app().test_client()
    c.post("/login", data={"username": "quality", "password": "admin"})
    yield c
    c.get("/logout")


@pytest.fixture
def user_client():
    c = _test_app().test_client()
    c.post("/login", data={"username": "shashi", "password": "admin"})
    yield c
    c.get("/logout")


@pytest.fixture
def sample_record():
    return {
        "id": "CMP-2024-0891", "type": "complaint", "sector": "Medical Device",
        "title": "Test complaint", "description": "Test description of a quality issue.",
        "priority": "High", "status": "Draft Generated",
        "site": "Site A", "owner": "Tester", "detectedDate": "2024-11-10",
        "regulatoryRef": ["21 CFR 820.198"], "createdBy": "admin",
    }
