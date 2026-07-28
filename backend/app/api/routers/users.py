import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import PERMISSION_CATALOG, require, valid_permission_set
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import Role, User
from app.schemas import (
    PermissionCatalogOut, RoleCreateIn, RoleOut, RoleUpdateIn, UserCreateIn,
    UserCreateOut, UserOut, UserUpdateIn,
)

router = APIRouter(prefix="/api", tags=["users"])

# The seeded super_admin role ("*:*") must never be edited or deleted via the
# API — that's the one role guaranteed to always have full access, and
# accidentally downgrading or removing it could lock every admin out.
_PROTECTED_ROLE = "super_admin"


def _user_out(u: User, **extra) -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "role": u.role.name, "is_active": u.is_active,
        "must_change_password": u.must_change_password, **extra,
    }


def _role_out(r: Role) -> dict:
    return {"id": r.id, "name": r.name, "description": r.description,
            "permissions": sorted(r.perm_set())}


def _check_permissions(perms: list[str]) -> None:
    unknown = [p for p in perms if p not in valid_permission_set()]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unknown permission(s): {', '.join(unknown)}")


@router.get("/permissions", response_model=list[PermissionCatalogOut])
def list_permissions(user: User = Depends(require("role:read"))):
    """The full catalog of assignable permissions, for the custom-role picker."""
    return PERMISSION_CATALOG


@router.get("/roles", response_model=list[RoleOut])
def list_roles(user: User = Depends(require("user:read")), db: Session = Depends(get_db)):
    return [_role_out(r) for r in db.scalars(select(Role).order_by(Role.name)).all()]


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(
    body: RoleCreateIn, user: User = Depends(require("role:create")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(Role).where(Role.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with this name already exists")
    _check_permissions(body.permissions)
    role = Role(name=body.name, description=body.description,
               permissions=",".join(body.permissions))
    db.add(role)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int, body: RoleUpdateIn, user: User = Depends(require("role:update")),
    db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.name == _PROTECTED_ROLE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The super_admin role cannot be modified")
    _check_permissions(body.permissions)
    role.permissions = ",".join(body.permissions)
    if body.description is not None:
        role.description = body.description
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(
    role_id: int, user: User = Depends(require("role:update")), db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.name == _PROTECTED_ROLE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The super_admin role cannot be deleted")
    if db.scalar(select(User).where(User.role_id == role_id)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Cannot delete a role that is assigned to one or more users")
    db.delete(role)
    db.commit()


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(require("user:read")), db: Session = Depends(get_db)):
    users = db.scalars(
        select(User).where(User.org_id == user.org_id).order_by(User.full_name)
    ).all()
    return [_user_out(u) for u in users]


@router.post("/users", response_model=UserCreateOut, status_code=201)
def create_user(
    body: UserCreateIn, user: User = Depends(require("user:create")),
    db: Session = Depends(get_db),
):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    role = db.scalar(select(Role).where(Role.name == body.role))
    if not role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown role: {body.role}")

    temp_password = secrets.token_urlsafe(9)
    new_user = User(
        org_id=user.org_id, role_id=role.id, email=email, full_name=body.full_name,
        hashed_password=hash_password(temp_password), must_change_password=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return _user_out(new_user, temp_password=temp_password)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdateIn, user: User = Depends(require("user:update")),
    db: Session = Depends(get_db),
):
    """Deactivate/reactivate a user — e.g. when someone leaves the org. This
    revokes their access immediately (checked fresh on every request) without
    deleting their record, so past journal entries/invoices/audit history they
    created stay correctly attributed."""
    target = db.get(User, user_id)
    if not target or target.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == user.id and not body.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "You can't deactivate your own account — ask another admin.")
    target.is_active = body.is_active
    db.commit()
    db.refresh(target)
    return _user_out(target)
