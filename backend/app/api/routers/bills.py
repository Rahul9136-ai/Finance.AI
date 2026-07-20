from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.user import User
from app.schemas import (
    BillDistributeIn, BillItemsPostIn, BillPostIn, ClassifyItemsIn, InvoiceOut,
)
from app.services import bills, tax_rules
from app.services.ledger import PostingError

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.post("/classify")
def classify(body: ClassifyItemsIn, user: User = Depends(require("invoice:read"))):
    """Classify line items by tax rules -> category, HSN, GST%, GL account, and a
    per-category distribution preview. No posting."""
    items = [i.model_dump() for i in body.items]
    return bills.classify_bill_items(items, tds_rate=body.tds_rate, tds_amount=body.tds_amount)


@router.get("/tax-rules")
def list_tax_rules(user: User = Depends(require("invoice:read"))):
    """The tax-rules catalog (category, HSN, GST rate, GL account)."""
    return [
        {"category": r.category, "hsn": r.hsn, "gst_rate": r.gst_rate,
         "account_code": r.account_code, "keywords": list(r.keywords)}
        for r in tax_rules.RULES
    ]


@router.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    user: User = Depends(require("invoice:read")),
):
    """Parse an uploaded bill (PDF/Excel/CSV) → extracted fields + a first-pass
    distribution the user can review and edit before posting."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB).")
    try:
        parsed = bills.parse_bill(file.filename or "", content)
    except Exception as e:
        raise HTTPException(422, f"Could not parse file: {e}")

    # Prefer an explicitly stated taxable value over inferring it from the
    # total (which, with TDS, is the net payable — not base + GST).
    desc = parsed.get("text_preview", "") or file.filename or ""
    dist = None
    if parsed["base"]:
        dist = bills.distribute(base=parsed["base"], gst_amount=parsed["gst"] or None,
                                tds_amount=parsed["tds"] or None, description=desc)
    elif parsed["gross"]:
        dist = bills.distribute(gross=parsed["gross"], gst_amount=parsed["gst"] or None,
                                tds_amount=parsed["tds"] or None, description=desc)

    return {"parsed": parsed, "distribution": dist.to_dict() if dist else None}


@router.post("/distribute")
def distribute(
    body: BillDistributeIn,
    user: User = Depends(require("invoice:read")),
):
    """Live preview: recompute the section split as the user edits amounts."""
    try:
        dist = bills.distribute(**body.model_dump())
        return dist.to_dict()
    except PostingError as e:
        raise HTTPException(422, str(e))


@router.post("", status_code=201)
def create_bill(
    body: BillPostIn,
    user: User = Depends(require("invoice:post")),
    db: Session = Depends(get_db),
):
    """Post a bill: auto-capture the vendor, distribute across sections, and write
    the balanced journal. Returns the invoice plus any newly-created vendor."""
    try:
        dist = bills.distribute(
            base=body.base, gst_amount=body.gst_amount,
            tds_amount=body.tds_amount, description=body.description,
        )
        inv, vendor, vendor_created = bills.post_bill(
            db, org_id=user.org_id, vendor_id=body.vendor_id, number=body.number,
            issue_date=body.issue_date, due_date=body.due_date,
            entry_mode=body.entry_mode, dist=dist, description=body.description,
            vendor_name=body.vendor_name, vendor_gstin=body.vendor_gstin,
        )
        db.commit()
        db.refresh(inv)
        return {
            "invoice": InvoiceOut.model_validate(inv).model_dump(mode="json"),
            "vendor": ({"id": vendor.id, "name": vendor.name, "gstin": vendor.gstin}
                       if vendor else None),
            "vendor_created": vendor_created,
        }
    except PostingError as e:
        db.rollback()
        raise HTTPException(422, str(e))


@router.post("/items", status_code=201)
def create_bill_items(
    body: BillItemsPostIn,
    user: User = Depends(require("invoice:post")),
    db: Session = Depends(get_db),
):
    """Post an itemised bill — each item is tax-classified and posted to its own
    category expense account, with per-item GST rolled into GST Input."""
    try:
        inv, vendor, vendor_created, result = bills.post_bill_items(
            db, org_id=user.org_id, vendor_id=body.vendor_id, number=body.number,
            issue_date=body.issue_date, due_date=body.due_date, entry_mode=body.entry_mode,
            items=[i.model_dump() for i in body.items],
            tds_rate=body.tds_rate, tds_amount=body.tds_amount,
            vendor_name=body.vendor_name, vendor_gstin=body.vendor_gstin,
        )
        db.commit()
        db.refresh(inv)
        return {
            "invoice": InvoiceOut.model_validate(inv).model_dump(mode="json"),
            "vendor": ({"id": vendor.id, "name": vendor.name, "gstin": vendor.gstin}
                       if vendor else None),
            "vendor_created": vendor_created,
            "classification": result,
        }
    except PostingError as e:
        db.rollback()
        raise HTTPException(422, str(e))
