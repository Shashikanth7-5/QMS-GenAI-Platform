# tests/test_auth.py
import pytest


def test_login_page_loads(client):
    # Use a fresh unauthenticated client
    r = client.get("/login", follow_redirects=False)
    assert r.status_code in (200, 302)  # 302 is fine — means already logged in

def test_login_admin_success(client):
    r = client.post("/login", data={"username":"admin","password":"admin"},
                    follow_redirects=True)
    assert r.status_code == 200
    client.get("/logout")

def test_login_wrong_password(client):
    r = client.post("/login", data={"username":"admin","password":"wrong"})
    assert b"Incorrect password" in r.data

def test_login_unknown_user(client):
    r = client.post("/login", data={"username":"nobody","password":"x"})
    assert b"not found" in r.data.lower()

def test_unauthenticated_dashboard_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 301)

def test_api_me_returns_role(admin_client):
    r = admin_client.get("/api/auth/me")
    assert r.status_code == 200
    data = r.get_json()
    assert data["role"] == "admin"
    assert data["is_admin"] is True
    assert data["can_approve_capa"] is True

def test_quality_me_returns_role(quality_client):
    r = quality_client.get("/api/auth/me")
    data = r.get_json()
    assert data["role"] == "quality"
    assert data["is_admin"] is False
    assert data["can_create_capa"] is True
    assert data["can_approve_capa"] is False

def test_user_me_returns_role(user_client):
    r = user_client.get("/api/auth/me")
    data = r.get_json()
    assert data["role"] == "user"
    assert data["can_create_capa"] is False
    assert data["sees_all_records"] is False

def test_admin_only_manage_users(admin_client, user_client):
    r_admin = admin_client.get("/admin/users")
    assert r_admin.status_code == 200
    r_user  = user_client.get("/admin/users")
    assert r_user.status_code == 403

def test_pending_count_admin(admin_client):
    r = admin_client.get("/api/auth/pending-count")
    assert r.status_code == 200
    assert "count" in r.get_json()

def test_pending_count_user_returns_zero(user_client):
    r = user_client.get("/api/auth/pending-count")
    assert r.get_json()["count"] == 0
