from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require
from app.db.session import get_db
from app.models.journal import JournalEntry
from app.models.user import User
from app.schemas import JournalEntryIn, JournalEntryOut
from app.services.ledger import LineInput, PostingError, post_entry, reverse_entry

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("", response_model=list[JournalEntryOut])
def list_entries(
    limit: int = 50, offset: int = 0,
    user: User = Depends(require("journal:read")), db: Session = Depends(get_db),
):
    return db.scalars(
        select(JournalEntry)
        .where(JournalEntry.org_id == user.org_id)
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .limit(min(limit, 200)).offset(offset)
    ).all()


@router.post("", response_model=JournalEntryOut, status_code=201)
def create_entry(
    body: JournalEntryIn,
    user: User = Depends(require("journal:post")), db: Session = Depends(get_db),
):
    try:
        entry = post_entry(
            db, org_id=user.org_id, entry_date=body.entry_date, memo=body.memo,
            lines=[LineInput(l.account_id, l.debit, l.credit, l.description)
                   for l in body.lines],
            source="manual",
        )
        db.commit()
        db.refresh(entry)
        return entry
    except PostingError as e:
        db.rollback()
        raise HTTPException(422, str(e))


@router.post("/{entry_id}/reverse", response_model=JournalEntryOut)
def reverse(
    entry_id: int,
    user: User = Depends(require("journal:post")), db: Session = Depends(get_db),
):
    entry = db.get(JournalEntry, entry_id)
    if not entry or entry.org_id != user.org_id:
        raise HTTPException(404, "Entry not found")
    try:
        rev = reverse_entry(db, entry=entry)
        db.commit()
        db.refresh(rev)
        return rev
    except PostingError as e:
        db.rollback()
        raise HTTPException(422, str(e))
