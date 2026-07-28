from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas import ChangePasswordIn, MeOut, RefreshIn, Token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")
    return Token(
        access_token=create_access_token(user.id, user.org_id, user.role.name),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=Token)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    # Refresh token travels in the JSON body, never the query string.
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return Token(
        access_token=create_access_token(user.id, user.org_id, user.role.name),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(
        id=user.id, email=user.email, full_name=user.full_name, org_id=user.org_id,
        role=user.role.name, permissions=sorted(user.role.perm_set()),
        must_change_password=user.must_change_password,
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn, user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    return {"ok": True}
