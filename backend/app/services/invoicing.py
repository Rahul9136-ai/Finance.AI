"""Invoice & payment lifecycle — each posting auto-generates a journal entry."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceLine, Payment
from app.models.org import Organization
from app.models.party import Customer, Vendor
from app.services import accounts as acct
from app.services import gst as gst_mod
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
    org_row = db.get(Organization, org)
    own_state = gst_mod.resolve_state(org_row.state_code if org_row else None,
                                      org_row.gstin if org_row else None)
    gst_split = gst_mod.GstSplit()

    if inv.kind == "AR":
        customer = db.get(Customer, inv.customer_id) if inv.customer_id else None
        cp_state = gst_mod.resolve_state(customer.state_code if customer else None,
                                         customer.gstin if customer else None)
        gst_split = gst_mod.split_gst(money(inv.tax_total), own_state, cp_state)

        # Dr Accounts Receivable ; Cr Sales + Cr GST Output (CGST/SGST or IGST)
        lines = [LineInput(acct.std(db, org, "ar").id, debit=money(inv.total),
                           description=f"AR {inv.number}")]
        # revenue split by line to allow multiple revenue accounts later
        lines.append(LineInput(acct.std(db, org, "sales").id,
                               credit=money(inv.subtotal), description="Sales revenue"))
        for row in gst_mod.gst_line_sections(gst_split, direction="output"):
            lines.append(LineInput(acct.by_code(db, org, row["account_code"]).id,
                                   credit=money(row["amount"]), description=row["section"]))
    else:  # AP bill
        vendor = db.get(Vendor, inv.vendor_id) if inv.vendor_id else None
        cp_state = gst_mod.resolve_state(vendor.state_code if vendor else None,
                                         vendor.gstin if vendor else None)
        gst_split = gst_mod.split_gst(money(inv.tax_total), own_state, cp_state)

        # Dr Expense + Dr GST Input (CGST/SGST or IGST) ; Cr Accounts Payable
        lines = [LineInput(acct.std(db, org, "opex").id, debit=money(inv.subtotal),
                           description=f"AP {inv.number}")]
        for row in gst_mod.gst_line_sections(gst_split, direction="input"):
            lines.append(LineInput(acct.by_code(db, org, row["account_code"]).id,
                                   debit=money(row["amount"]), description=row["section"]))
        lines.append(LineInput(acct.std(db, org, "ap").id,
                               credit=money(inv.total), description="Accounts payable"))

    inv.ai_meta = json.dumps({"gst": gst_split.to_dict()})
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
