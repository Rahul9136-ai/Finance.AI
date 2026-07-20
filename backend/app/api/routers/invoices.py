from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.invoice import Invoice, InvoiceLine
from app.models.user import User
from app.schemas import InvoiceIn, InvoiceOut, PaymentIn
from app.services.invoicing import post_invoice, record_payment, refresh_totals
from app.services.ledger import PostingError

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _get(db: Session, org_id: int, invoice_id: int) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if not inv or inv.org_id != org_id:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    kind: str | None = None, status: str | None = None,
    user: User = Depends(require("invoice:read")), db: Session = Depends(get_db),
):
    q = select(Invoice).where(Invoice.org_id == user.org_id)
    if kind:
        q = q.where(Invoice.kind == kind)
    if status:
        q = q.where(Invoice.status == status)
    return db.scalars(q.order_by(Invoice.issue_date.desc(), Invoice.id.desc())).all()


@router.post("", response_model=InvoiceOut, status_code=201)
def create_invoice(
    body: InvoiceIn, user: User = Depends(require("invoice:create")),
    db: Session = Depends(get_db),
):
    inv = Invoice(
        org_id=user.org_id, kind=body.kind, number=body.number,
        vendor_id=body.vendor_id, customer_id=body.customer_id,
        issue_date=body.issue_date, due_date=body.due_date, status="draft",
    )
    for l in body.lines:
        inv.lines.append(InvoiceLine(**l.model_dump()))
    refresh_totals(inv)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/post", response_model=InvoiceOut)
def post(invoice_id: int, user: User = Depends(require("invoice:post")),
         db: Session = Depends(get_db)):
    inv = _get(db, user.org_id, invoice_id)
    try:
        post_invoice(db, inv)
        db.commit()
        db.refresh(inv)
        return inv
    except PostingError as e:
        db.rollback()
        raise HTTPException(422, str(e))


@router.post("/{invoice_id}/pay", response_model=InvoiceOut)
def pay(invoice_id: int, body: PaymentIn,
        user: User = Depends(require("payment:create")), db: Session = Depends(get_db)):
    inv = _get(db, user.org_id, invoice_id)
    try:
        record_payment(db, inv, amount=body.amount, pay_date=body.pay_date,
                       method=body.method, reference=body.reference)
        db.commit()
        db.refresh(inv)
        return inv
    except PostingError as e:
        db.rollback()
        raise HTTPException(422, str(e))
