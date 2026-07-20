"""Invoice & payment lifecycle — each posting auto-generates a journal entry."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceLine, Payment
from app.services import accounts as acct
from app.services.ledger import LineInput, money, post_entry, PostingError


def compute_totals(lines: list[InvoiceLine]) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = Decimal("0")
    tax = Decimal("0")
    for l in lines:
        base = money(l.line_subtotal)
        subtotal += base
        tax += money(base * Decimal(str(l.tax_rate)) / Decimal("100"))
    subtotal = money(subtotal)
    tax = money(tax)
    return subtotal, tax, money(subtotal + tax)


def refresh_totals(inv: Invoice) -> None:
    inv.subtotal, inv.tax_total, inv.total = (float(x) for x in compute_totals(inv.lines))


def post_invoice(db: Session, inv: Invoice) -> Invoice:
    """Post an invoice to the ledger and open it for settlement."""
    if inv.status != "draft":
        raise PostingError("Only draft invoices can be posted.")
    refresh_totals(inv)
    if money(inv.total) <= 0:
        raise PostingError("Invoice total must be positive.")

    org = inv.org_id
    if inv.kind == "AR":
        # Dr Accounts Receivable ; Cr Sales + Cr GST Output
        lines = [LineInput(acct.std(db, org, "ar").id, debit=money(inv.total),
                           description=f"AR {inv.number}")]
        # revenue split by line to allow multiple revenue accounts later
        lines.append(LineInput(acct.std(db, org, "sales").id,
                               credit=money(inv.subtotal), description="Sales revenue"))
        if money(inv.tax_total) > 0:
            lines.append(LineInput(acct.std(db, org, "gst_output").id,
                                   credit=money(inv.tax_total), description="GST output"))
    else:  # AP bill
        # Dr Expense + Dr GST Input ; Cr Accounts Payable
        lines = [LineInput(acct.std(db, org, "opex").id, debit=money(inv.subtotal),
                           description=f"AP {inv.number}")]
        if money(inv.tax_total) > 0:
            lines.append(LineInput(acct.std(db, org, "gst_input").id,
                                   debit=money(inv.tax_total), description="GST input"))
        lines.append(LineInput(acct.std(db, org, "ap").id,
                               credit=money(inv.total), description="Accounts payable"))

    entry = post_entry(
        db, org_id=org, entry_date=inv.issue_date,
        memo=f"{inv.kind} invoice {inv.number}", lines=lines,
        source="invoice", ref=inv.number,
    )
    inv.journal_entry_id = entry.id
    inv.status = "open"
    return inv


def record_payment(
    db: Session, inv: Invoice, *, amount: float, pay_date: date,
    method: str = "bank", reference: str = "",
) -> Payment:
    """Record a payment against an open invoice and post the settlement entry."""
    if inv.status not in ("open", "partial"):
        raise PostingError(f"Cannot pay an invoice with status '{inv.status}'.")
    amt = money(amount)
    outstanding = money(inv.total) - money(inv.amount_paid)
    if amt <= 0:
        raise PostingError("Payment amount must be positive.")
    if amt > outstanding:
        raise PostingError(f"Payment {amt} exceeds outstanding {outstanding}.")

    org = inv.org_id
    bank = acct.std(db, org, "bank").id
    if inv.kind == "AR":  # Dr Bank ; Cr AR
        lines = [LineInput(bank, debit=amt, description=f"Receipt {inv.number}"),
                 LineInput(acct.std(db, org, "ar").id, credit=amt, description="AR settled")]
    else:  # AP payment: Dr AP ; Cr Bank
        lines = [LineInput(acct.std(db, org, "ap").id, debit=amt, description="AP settled"),
                 LineInput(bank, credit=amt, description=f"Payment {inv.number}")]

    entry = post_entry(
        db, org_id=org, entry_date=pay_date,
        memo=f"Payment {method} for {inv.number}", lines=lines,
        source="payment", ref=reference or inv.number,
    )
    pay = Payment(
        org_id=org, invoice_id=inv.id, pay_date=pay_date, amount=amt,
        method=method, reference=reference, journal_entry_id=entry.id,
    )
    db.add(pay)

    inv.amount_paid = float(money(inv.amount_paid) + amt)
    inv.status = "paid" if money(inv.amount_paid) >= money(inv.total) else "partial"
    return pay
