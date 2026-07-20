from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.user import User
from app.services import dashboard as dash

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/kpis")
def kpis(user: User = Depends(require("dashboard:read")), db: Session = Depends(get_db)):
    return dash.kpis(db, user.org_id)


@router.get("/aging")
def aging(kind: str = "AR", user: User = Depends(require("dashboard:read")),
          db: Session = Depends(get_db)):
    return dash.aging(db, user.org_id, kind)


@router.get("/revenue-series")
def revenue_series(months: int = 6, user: User = Depends(require("dashboard:read")),
                   db: Session = Depends(get_db)):
    return dash.revenue_series(db, user.org_id, months)


@router.get("/pnl")
def pnl(user: User = Depends(require("report:read")), db: Session = Depends(get_db)):
    return dash.pnl(db, user.org_id)


@router.get("/balance-sheet")
def balance_sheet(user: User = Depends(require("report:read")), db: Session = Depends(get_db)):
    return dash.balance_sheet(db, user.org_id)
