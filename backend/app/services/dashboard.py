"""Dashboard aggregates and financial-statement figures, from posted data."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.services import accounts as acct
from app.services.ledger import account_balance, balance_by_type, money


def _outstanding(db: Session, org_id: int, kind: str) -> Decimal:
    rows = db.execute(
        select(Invoice.total, Invoice.amount_paid).where(
            Invoice.org_id == org_id,
            Invoice.kind == kind,
            Invoice.status.in_(("open", "partial")),
        )
    ).all()
    return money(sum((money(t) - money(p) for t, p in rows), Decimal("0")))


def _sum_codes(db: Session, org_id: int, codes: list[str]) -> Decimal:
    total = Decimal("0")
    for code in codes:
        a = acct.by_code(db, org_id, code)
        if a:
            total += account_balance(db, org_id=org_id, account_id=a.id)
    return total


# GST Output Payable (liability) and GST Input Credit (asset) each have a
# proper CGST/SGST/IGST account plus an "unclassified" suspense account used
# only when a party's state couldn't be determined — see services/gst.py.
_GST_OUTPUT_CODES = ["2100", "2101", "2102", "2103"]
_GST_INPUT_CODES = ["1300", "1301", "1302", "1303"]


def kpis(db: Session, org_id: int) -> dict:
    bank = acct.by_code(db, org_id, "1010")
    cash = acct.by_code(db, org_id, "1000")

    cash_balance = Decimal("0")
    for a in (bank, cash):
        if a:
            cash_balance += account_balance(db, org_id=org_id, account_id=a.id)

    by_type = balance_by_type(db, org_id=org_id)
    revenue = by_type.get("income", Decimal("0"))
    expense = by_type.get("expense", Decimal("0"))

    gst_payable = (_sum_codes(db, org_id, _GST_OUTPUT_CODES)
                   - _sum_codes(db, org_id, _GST_INPUT_CODES))

    return {
        "cash_balance": float(cash_balance),
        "receivables": float(_outstanding(db, org_id, "AR")),
        "payables": float(_outstanding(db, org_id, "AP")),
        "revenue": float(revenue),
        "expenses": float(expense),
        "profit": float(revenue - expense),
        "gst_due": float(money(gst_payable)),
    }


def aging(db: Session, org_id: int, kind: str, today: date | None = None) -> dict:
    """Bucketed aging for AR or AP: current, 1-30, 31-60, 61-90, 90+."""
    today = today or date.today()
    buckets = {"current": Decimal("0"), "1-30": Decimal("0"), "31-60": Decimal("0"),
               "61-90": Decimal("0"), "90+": Decimal("0")}
    rows = db.execute(
        select(Invoice.total, Invoice.amount_paid, Invoice.due_date).where(
            Invoice.org_id == org_id, Invoice.kind == kind,
            Invoice.status.in_(("open", "partial")),
        )
    ).all()
    for total, paid, due in rows:
        bal = money(total) - money(paid)
        overdue = (today - due).days
        if overdue <= 0:
            buckets["current"] += bal
        elif overdue <= 30:
            buckets["1-30"] += bal
        elif overdue <= 60:
            buckets["31-60"] += bal
        elif overdue <= 90:
            buckets["61-90"] += bal
        else:
            buckets["90+"] += bal
    return {k: float(v) for k, v in buckets.items()}


def pnl(db: Session, org_id: int) -> dict:
    by_type = balance_by_type(db, org_id=org_id)
    income = by_type.get("income", Decimal("0"))
    expense = by_type.get("expense", Decimal("0"))
    return {"income": float(income), "expense": float(expense),
            "net_profit": float(income - expense)}


def balance_sheet(db: Session, org_id: int) -> dict:
    by_type = balance_by_type(db, org_id=org_id)
    assets = by_type.get("asset", Decimal("0"))
    liabilities = by_type.get("liability", Decimal("0"))
    equity = by_type.get("equity", Decimal("0"))
    retained = by_type.get("income", Decimal("0")) - by_type.get("expense", Decimal("0"))
    return {
        "assets": float(assets),
        "liabilities": float(liabilities),
        "equity": float(equity),
        "retained_earnings": float(retained),
        "balanced": float(money(assets)) == float(money(liabilities + equity + retained)),
    }


def revenue_series(db: Session, org_id: int, months: int = 6) -> list[dict]:
    """Monthly revenue vs expense for charts (posted AR/AP invoices)."""
    out = []
    this_month = date.today().replace(day=1)
    for i in range(months - 1, -1, -1):
        # Calendar-month arithmetic — fixed-day offsets drift across months of
        # differing length (would skip/duplicate a month).
        month_start = this_month - relativedelta(months=i)
        nxt = month_start + relativedelta(months=1)
        rev = db.scalar(
            select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
                Invoice.org_id == org_id, Invoice.kind == "AR",
                Invoice.status != "draft",
                Invoice.issue_date >= month_start, Invoice.issue_date < nxt,
            )
        )
        exp = db.scalar(
            select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
                Invoice.org_id == org_id, Invoice.kind == "AP",
                Invoice.status != "draft",
                Invoice.issue_date >= month_start, Invoice.issue_date < nxt,
            )
        )
        out.append({"month": month_start.strftime("%b %Y"),
                    "revenue": float(money(rev)), "expense": float(money(exp))})
    return out
