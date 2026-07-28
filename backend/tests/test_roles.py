"""Custom role management: only an admin can define roles, only real
enforced permissions can be assigned, and the built-in super_admin role is
protected from being edited/deleted (it's the one role guaranteed full
access — losing it could lock every admin out)."""
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
    yield s, org, viewer_role
    s.close()
    Base.metadata.drop_all(engine)


def _token(email: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(email, password):
    return {"Authorization": f"Bearer {_token(email, password)}"}


def test_permission_catalog_is_returned(setup):
    r = client.get("/api/permissions", headers=_auth("admin@t.io", "adminpass"))
    assert r.status_code == 200
    catalog = r.json()
    assert any(c["resource"] == "invoice" for c in catalog)


def test_admin_can_create_custom_role(setup):
    headers = _auth("admin@t.io", "adminpass")
    r = client.post("/api/roles", json={
        "name": "ap_clerk_custom", "description": "AP data entry only",
        "permissions": ["invoice:read", "invoice:create", "vendor:read"],
    }, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "ap_clerk_custom"
    assert sorted(body["permissions"]) == ["invoice:create", "invoice:read", "vendor:read"]


def test_create_role_rejects_unknown_permission(setup):
    headers = _auth("admin@t.io", "adminpass")
    r = client.post("/api/roles", json={
        "name": "bad_role", "permissions": ["invoice:delete_everything"],
    }, headers=headers)
    assert r.status_code == 400


def test_create_role_rejects_duplicate_name(setup):
    headers = _auth("admin@t.io", "adminpass")
    r = client.post("/api/roles", json={"name": "viewer", "permissions": []}, headers=headers)
    assert r.status_code == 409


def test_non_admin_cannot_create_role(setup):
    headers = _auth("viewer@t.io", "viewerpass")
    r = client.post("/api/roles", json={"name": "x", "permissions": []}, headers=headers)
    assert r.status_code == 403


def test_new_user_with_custom_role_gets_exactly_its_permissions(setup):
    headers = _auth("admin@t.io", "adminpass")
    client.post("/api/roles", json={
        "name": "ap_clerk_custom",
        "permissions": ["invoice:read", "invoice:create"],
    }, headers=headers)
    created = client.post("/api/users", json={
        "email": "clerk@t.io", "full_name": "Clerk", "role": "ap_clerk_custom",
    }, headers=headers)
    assert created.status_code == 201, created.text
    temp_password = created.json()["temp_password"]
    me = client.get("/api/auth/me", headers=_auth("clerk@t.io", temp_password))
    assert sorted(me.json()["permissions"]) == ["invoice:create", "invoice:read"]


def test_cannot_edit_super_admin_role(setup):
    headers = _auth("admin@t.io", "adminpass")
    roles = client.get("/api/roles", headers=headers).json()
    admin_role = next(r for r in roles if r["name"] == "super_admin")
    r = client.patch(f"/api/roles/{admin_role['id']}",
                     json={"permissions": ["dashboard:read"]}, headers=headers)
    assert r.status_code == 403


def test_cannot_delete_super_admin_role(setup):
    headers = _auth("admin@t.io", "adminpass")
    roles = client.get("/api/roles", headers=headers).json()
    admin_role = next(r for r in roles if r["name"] == "super_admin")
    r = client.delete(f"/api/roles/{admin_role['id']}", headers=headers)
    assert r.status_code == 403


def test_update_role_permissions(setup):
    headers = _auth("admin@t.io", "adminpass")
    created = client.post("/api/roles", json={
        "name": "editable_role", "permissions": ["dashboard:read"],
    }, headers=headers).json()
    r = client.patch(f"/api/roles/{created['id']}",
                     json={"permissions": ["dashboard:read", "report:read"]}, headers=headers)
    assert r.status_code == 200
    assert sorted(r.json()["permissions"]) == ["dashboard:read", "report:read"]


def test_cannot_delete_role_assigned_to_a_user(setup, ):
    headers = _auth("admin@t.io", "adminpass")
    r = client.delete(f"/api/roles/{setup[2].id}", headers=headers)  # viewer role, has a user
    assert r.status_code == 409


def test_delete_unused_role(setup):
    headers = _auth("admin@t.io", "adminpass")
    created = client.post("/api/roles", json={
        "name": "throwaway_role", "permissions": [],
    }, headers=headers).json()
    r = client.delete(f"/api/roles/{created['id']}", headers=headers)
    assert r.status_code == 204
    roles = client.get("/api/roles", headers=headers).json()
    assert not any(r["name"] == "throwaway_role" for r in roles)
