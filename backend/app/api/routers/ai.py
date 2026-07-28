from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai import skills
from app.ai.provider import active_provider
from app.core.rbac import require
from app.db.session import get_db
from app.models.org import Organization
from app.models.user import User
from app.schemas import ChatIn, ExpenseCategorizeIn, FraudCheckIn, InvoiceReadIn

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status(user: User = Depends(require("ai:read"))):
    return {"provider": active_provider()}


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(require("ai:read")),
         db: Session = Depends(get_db)):
    return skills.chat(db, user.org_id, body.question)


@router.post("/read-invoice")
def read_invoice(body: InvoiceReadIn, user: User = Depends(require("ai:read")),
                 db: Session = Depends(get_db)):
    org = db.get(Organization, user.org_id)
    return skills.read_invoice(body.text, own_gstin=org.gstin if org else None)


@router.post("/categorize")
def categorize(body: ExpenseCategorizeIn, user: User = Depends(require("ai:read"))):
    return skills.categorize_expense(body.description, body.amount)


@router.post("/fraud-check")
def fraud_check(body: FraudCheckIn, user: User = Depends(require("ai:read")),
                db: Session = Depends(get_db)):
    return skills.score_fraud(
        db, user.org_id, amount=body.amount, when=body.when,
        vendor_id=body.vendor_id, description=body.description,
    )


@router.get("/forecast")
def forecast(horizon_days: int = 90, user: User = Depends(require("ai:read")),
             db: Session = Depends(get_db)):
    return skills.forecast_cashflow(db, user.org_id, horizon_days)
