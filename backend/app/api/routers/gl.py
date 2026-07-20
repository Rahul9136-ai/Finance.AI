from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.user import User
from app.services.ledger import PostingError, account_ledger, trial_balance

router = APIRouter(prefix="/api/ledger", tags=["general-ledger"])


@router.get("/trial-balance")
def get_trial_balance(
    user: User = Depends(require("account:read")), db: Session = Depends(get_db)
):
    return trial_balance(db, org_id=user.org_id)


@router.get("/account/{account_id}")
def get_account_ledger(
    account_id: int,
    user: User = Depends(require("account:read")), db: Session = Depends(get_db),
):
    try:
        return account_ledger(db, org_id=user.org_id, account_id=account_id)
    except PostingError as e:
        raise HTTPException(404, str(e))
