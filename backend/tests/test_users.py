"""User-provisioning tests: only an admin can create accounts, temp passwords
force a reset on first login, and users can only change their own password
with the correct current password."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.org import Organization  # noqa: E402
from app.models.user import Role, User  # noqa: E402

client = TestClient(app)


@pytest.fixture()
def setup():
    Base.metadata.create_all(engine)
    s = SessionLocal()
    org = Organization(name="T")
    s.add(org)
    s.flush()
    admin_role = Role(name="super_admin", permissions="*:*")
    viewer_role = Role(name="viewer", permissions="dashboard:read")
    s.add_all([admin_role, viewer_role])
    s.flush()
    admin = User(org_id=org.id, role_id=admin_role.id, email="admin@t.io",
                 full_name="Admin", hashed_password=hash_password("adminpass"),
                 must_change_password=False)
    viewer = User(org_id=org.id, role_id=viewer_role.id, email="viewer@t.io",
                  full_name="Viewer", hashed_password=hash_password("viewerpass"),
                  must_change_password=False)
    s.add_all([admin, viewer])
    s.commit()
    yield s, org
    s.close()
    Base.metadata.drop_all(engine)


def _token(email: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_admin_can_create_user_with_temp_password(setup):
    token = _token("admin@t.io", "adminpass")
    r = client.post(
        "/api/users",
        json={"email": "newperson@t.io", "full_name": "New Person", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["must_change_password"] is True
    assert len(body["temp_password"]) >= 8

    login = client.post("/api/auth/login", data={"username": "newperson@t.io",
                                                   "password": body["temp_password"]})
    assert login.status_code == 200
    new_token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.json()["must_change_password"] is True


def test_non_admin_cannot_create_user(setup):
    token = _token("viewer@t.io", "viewerpass")
    r = client.post(
        "/api/users",
        json={"email": "x@t.io", "full_name": "X", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_duplicate_email_rejected(setup):
    token = _token("admin@t.io", "adminpass")
    r = client.post(
        "/api/users",
        json={"email": "viewer@t.io", "full_name": "Dup", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


def test_unknown_role_rejected(setup):
    token = _token("admin@t.io", "adminpass")
    r = client.post(
        "/api/users",
        json={"email": "y@t.io", "full_name": "Y", "role": "nonexistent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_change_password_clears_must_change_flag(setup):
    token = _token("admin@t.io", "adminpass")
    create = client.post(
        "/api/users",
        json={"email": "z@t.io", "full_name": "Z", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    temp_password = create.json()["temp_password"]
    new_token = _token("z@t.io", temp_password)
    headers = {"Authorization": f"Bearer {new_token}"}

    bad = client.post("/api/auth/change-password",
                       json={"current_password": "wrong", "new_password": "brandnewpass"},
                       headers=headers)
    assert bad.status_code == 401

    ok = client.post("/api/auth/change-password",
                      json={"current_password": temp_password, "new_password": "brandnewpass"},
                      headers=headers)
    assert ok.status_code == 200

    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["must_change_password"] is False

    relogin = client.post("/api/auth/login",
                           data={"username": "z@t.io", "password": "brandnewpass"})
    assert relogin.status_code == 200


def test_deactivate_revokes_access_immediately(setup):
    admin_token = _token("admin@t.io", "adminpass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(
        "/api/users",
        json={"email": "leaver@t.io", "full_name": "Leaver", "role": "viewer"},
        headers=admin_headers,
    )
    user_id = create.json()["id"]
    leaver_token = _token("leaver@t.io", create.json()["temp_password"])
    leaver_headers = {"Authorization": f"Bearer {leaver_token}"}

    # Works fine while active.
    assert client.get("/api/auth/me", headers=leaver_headers).status_code == 200

    r = client.patch(f"/api/users/{user_id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # The already-issued access token is rejected on the very next request.
    assert client.get("/api/auth/me", headers=leaver_headers).status_code == 401
    # Can't log in again either.
    relogin = client.post("/api/auth/login",
                           data={"username": "leaver@t.io", "password": "demo-irrelevant"})
    assert relogin.status_code in (401, 403)


def test_deactivated_user_can_be_reactivated(setup):
    admin_token = _token("admin@t.io", "adminpass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(
        "/api/users",
        json={"email": "boomerang@t.io", "full_name": "Boomerang", "role": "viewer"},
        headers=admin_headers,
    )
    user_id = create.json()["id"]
    temp_password = create.json()["temp_password"]

    client.patch(f"/api/users/{user_id}", json={"is_active": False}, headers=admin_headers)
    r = client.patch(f"/api/users/{user_id}", json={"is_active": True}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    relogin = client.post("/api/auth/login",
                           data={"username": "boomerang@t.io", "password": temp_password})
    assert relogin.status_code == 200


def test_cannot_deactivate_own_account(setup):
    admin_token = _token("admin@t.io", "adminpass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    me = client.get("/api/auth/me", headers=admin_headers).json()
    r = client.patch(f"/api/users/{me['id']}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 400


def test_non_admin_cannot_deactivate_users(setup):
    admin_token = _token("admin@t.io", "adminpass")
    create = client.post(
        "/api/users",
        json={"email": "target@t.io", "full_name": "Target", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_id = create.json()["id"]

    viewer_token = _token("viewer@t.io", "viewerpass")
    r = client.patch(f"/api/users/{user_id}", json={"is_active": False},
                     headers={"Authorization": f"Bearer {viewer_token}"})
    assert r.status_code == 403
