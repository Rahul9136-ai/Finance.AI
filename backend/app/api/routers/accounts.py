from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.account import Account
from app.models.user import User
from app.schemas import AccountBalanceOut, AccountOut
from app.services.ledger import account_balance

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(user: User = Depends(require("account:read")), db: Session = Depends(get_db)):
    return db.scalars(
        select(Account).where(Account.org_id == user.org_id).order_by(Account.code)
    ).all()


@router.get("/balances", response_model=list[AccountBalanceOut])
def balances(user: User = Depends(require("account:read")), db: Session = Depends(get_db)):
    accts = db.scalars(
        select(Account).where(Account.org_id == user.org_id).order_by(Account.code)
    ).all()
    out = []
    for a in accts:
        bal = float(account_balance(db, org_id=user.org_id, account_id=a.id))
        out.append(AccountBalanceOut(
            id=a.id, code=a.code, name=a.name, type=a.type,
            parent_id=a.parent_id, is_postable=a.is_postable, balance=bal,
        ))
    return out
