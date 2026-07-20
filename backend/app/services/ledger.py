"""The double-entry ledger engine — the integrity core of the ERP.

Every financial mutation in the system funnels through `post_entry`, which
guarantees Σdebits == Σcredits, postable-account-only lines, and org scoping.
Posted entries are immutable; corrections are reversing entries.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.account import Account, DEBIT_NORMAL
from app.models.journal import JournalEntry, JournalLine

CENTS = Decimal("0.01")


class PostingError(ValueError):
    """Raised when an entry violates accounting invariants."""


def money(v) -> Decimal:
    return Decimal(str(v)).quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass
class LineInput:
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str = ""


def post_entry(
    db: Session,
    *,
    org_id: int,
    entry_date: date,
    memo: str,
    lines: list[LineInput],
    source: str = "manual",
    ref: str = "",
    autoflush: bool = True,
) -> JournalEntry:
    """Validate and post a balanced journal entry. Does not commit."""
    if len(lines) < 2:
        raise PostingError("A journal entry needs at least two lines.")

    total_debit = sum((money(l.debit) for l in lines), Decimal("0"))
    total_credit = sum((money(l.credit) for l in lines), Decimal("0"))
    if total_debit != total_credit:
        raise PostingError(
            f"Unbalanced entry: debits {total_debit} != credits {total_credit}."
        )
    if total_debit == 0:
        raise PostingError("Entry total cannot be zero.")

    # Validate accounts belong to org and are postable.
    acct_ids = {l.account_id for l in lines}
    accounts = db.scalars(
        select(Account).where(Account.id.in_(acct_ids), Account.org_id == org_id)
    ).all()
    found = {a.id: a for a in accounts}
    for l in lines:
        acct = found.get(l.account_id)
        if acct is None:
            raise PostingError(f"Account {l.account_id} not found for this org.")
        if not acct.is_postable:
            raise PostingError(f"Account {acct.code} is a header and not postable.")
        if money(l.debit) < 0 or money(l.credit) < 0:
            raise PostingError("Debit/credit amounts must be non-negative.")
        if money(l.debit) > 0 and money(l.credit) > 0:
            raise PostingError("A line cannot have both a debit and a credit.")

    entry = JournalEntry(
        org_id=org_id,
        entry_date=entry_date,
        memo=memo,
        source=source,
        ref=ref,
        status="posted",
    )
    for l in lines:
        entry.lines.append(
            JournalLine(
                account_id=l.account_id,
                debit=money(l.debit),
                credit=money(l.credit),
                description=l.description,
            )
        )
    db.add(entry)
    if autoflush:
        db.flush()
    return entry


def reverse_entry(db: Session, *, entry: JournalEntry, on: date | None = None) -> JournalEntry:
    """Create and post a reversing entry that negates `entry`."""
    if entry.status != "posted":
        raise PostingError("Only posted entries can be reversed.")
    if entry.reversed_by is not None:
        raise PostingError("Entry already reversed.")

    rev_lines = [
        LineInput(
            account_id=l.account_id,
            debit=money(l.credit),
            credit=money(l.debit),
            description=f"Reversal: {l.description}",
        )
        for l in entry.lines
    ]
    reversal = post_entry(
        db,
        org_id=entry.org_id,
        entry_date=on or entry.entry_date,
        memo=f"Reversal of #{entry.id} — {entry.memo}",
        lines=rev_lines,
        source=entry.source,
        ref=f"REV-{entry.ref or entry.id}",
    )
    entry.status = "reversed"
    entry.reversed_by = reversal.id
    return reversal


def account_balance(db: Session, *, org_id: int, account_id: int) -> Decimal:
    """Signed balance in the account's normal direction (posted entries only)."""
    row = db.execute(
        select(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.org_id == org_id,
            # Reversed entries keep their real lines; the linked reversal offsets
            # them. Both must be counted so the net effect is zero.
            JournalEntry.status.in_(("posted", "reversed")),
        )
    ).one()
    debit, credit = money(row[0]), money(row[1])
    acct = db.get(Account, account_id)
    if acct and acct.type in DEBIT_NORMAL:
        return debit - credit
    return credit - debit


def balance_by_type(db: Session, *, org_id: int) -> dict[str, Decimal]:
    """Aggregate normal-balance totals per account type — powers statements."""
    rows = db.execute(
        select(
            Account.type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(Account.org_id == org_id, JournalEntry.status.in_(("posted", "reversed")))
        .group_by(Account.type)
    ).all()
    out: dict[str, Decimal] = {}
    for atype, debit, credit in rows:
        d, c = money(debit), money(credit)
        out[atype] = (d - c) if atype in DEBIT_NORMAL else (c - d)
    return out


def trial_balance(db: Session, *, org_id: int) -> dict:
    """Trial balance: every account's net balance placed in its natural column.

    Built from net-debit (Σdebit − Σcredit) per account, so the debit and credit
    columns are guaranteed to be equal (every posted entry balances)."""
    rows = db.execute(
        select(
            Account.id, Account.code, Account.name, Account.type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(Account.org_id == org_id, JournalEntry.status.in_(("posted", "reversed")))
        .group_by(Account.id, Account.code, Account.name, Account.type)
        .order_by(Account.code)
    ).all()

    accounts = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for aid, code, name, atype, debit, credit in rows:
        net = money(debit) - money(credit)  # net debit (can be negative)
        if net == 0:
            continue  # skip accounts with no net movement
        dr = net if net > 0 else Decimal("0")
        cr = -net if net < 0 else Decimal("0")
        total_debit += dr
        total_credit += cr
        accounts.append({
            "account_id": aid, "code": code, "name": name, "type": atype,
            "debit": float(dr), "credit": float(cr),
        })

    return {
        "accounts": accounts,
        "total_debit": float(money(total_debit)),
        "total_credit": float(money(total_credit)),
        "balanced": money(total_debit) == money(total_credit),
    }


def account_ledger(db: Session, *, org_id: int, account_id: int) -> dict:
    """Per-account ledger: chronological postings with a running balance in the
    account's normal direction (the classic drill-down)."""
    acct = db.get(Account, account_id)
    if acct is None or acct.org_id != org_id:
        raise PostingError("Account not found for this org.")

    rows = db.execute(
        select(
            JournalEntry.id, JournalEntry.entry_date, JournalEntry.ref,
            JournalEntry.memo, JournalEntry.status,
            JournalLine.debit, JournalLine.credit, JournalLine.description,
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.org_id == org_id,
            JournalEntry.status.in_(("posted", "reversed")),
        )
        .order_by(JournalEntry.entry_date, JournalEntry.id)
    ).all()

    debit_normal = acct.type in DEBIT_NORMAL
    running = Decimal("0")
    lines = []
    for eid, edate, ref, memo, status, debit, credit, desc in rows:
        d, c = money(debit), money(credit)
        running += (d - c) if debit_normal else (c - d)
        lines.append({
            "entry_id": eid, "date": edate.isoformat(), "ref": ref,
            "memo": desc or memo, "status": status,
            "debit": float(d), "credit": float(c), "balance": float(money(running)),
        })

    return {
        "account": {"id": acct.id, "code": acct.code, "name": acct.name,
                    "type": acct.type, "normal": "debit" if debit_normal else "credit"},
        "lines": lines,
        "closing_balance": float(money(running)),
    }
