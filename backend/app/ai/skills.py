"""Finance AI skills. Each is *grounded* in real DB data and degrades to
deterministic logic when no LLM key is present."""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import active_provider, complete
from app.models.invoice import Invoice
from app.services import dashboard
from app.services.ledger import money

# ---------------------------------------------------------------------------
# 1. Invoice reader (OCR/extraction)
# ---------------------------------------------------------------------------
_AMOUNT_RE = re.compile(r"(?:total|amount due|grand total)[^\d]{0,12}([\d,]+\.?\d*)", re.I)
_DATE_RE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
_GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d])\b")
# A document number must contain a digit (so the literal word "Invoice" can't
# match). Prefer a labelled number, else any alnum token with letters + digits.
_NUM_LABELLED = re.compile(
    r"(?:invoice|bill|inv)\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z]{0,4}[-/]?\d[A-Z0-9\-/]*)",
    re.I,
)
_NUM_TOKEN = re.compile(r"\b([A-Z]{2,}[-/]?\d{2,}[A-Z0-9\-/]*)\b")


def _extract_number(text: str) -> str | None:
    m = _NUM_LABELLED.search(text)
    if m and any(c.isdigit() for c in m.group(1)):
        return m.group(1).strip(":#-")
    m = _NUM_TOKEN.search(text)
    return m.group(1) if m else None


def read_invoice(raw_text: str) -> dict:
    """Extract structured fields from raw invoice text (regex heuristics;
    an LLM refines them when available)."""
    text = raw_text or ""
    amounts = [float(a.replace(",", "")) for a in _AMOUNT_RE.findall(text)]
    total = max(amounts) if amounts else None
    result = {
        "vendor_gstin": (_GSTIN_RE.search(text) or [None]) and (
            _GSTIN_RE.search(text).group(1) if _GSTIN_RE.search(text) else None
        ),
        "invoice_number": _extract_number(text),
        "invoice_date": (_DATE_RE.search(text).group(1) if _DATE_RE.search(text) else None),
        "total": total,
        "confidence": 0.6 if total else 0.3,
        "engine": "rules",
    }
    return result


_BILL_SCHEMA = (
    '{"vendor_name":str|null,"vendor_gstin":str|null,"invoice_number":str|null,'
    '"invoice_date":"DD/MM/YYYY"|null,"taxable_base":number|null,"cgst":number|null,'
    '"sgst":number|null,"igst":number|null,"total_gst":number|null,"tds":number|null,'
    '"grand_total":number|null,"net_payable":number|null,'
    '"line_items":[{"description":str,"amount":number}]}'
)


def llm_extract_bill(text: str) -> dict | None:
    """Extract structured bill fields with an LLM (much more accurate on arbitrary
    layouts). Returns a parsed dict, or None if no provider/failed. Numbers only —
    no currency symbols or commas."""
    if active_provider() == "rules" or not (text or "").strip():
        return None
    out = complete(
        "Extract the fields from this vendor bill / tax invoice as STRICT JSON "
        f"matching exactly this shape (numbers with no commas or currency symbols, "
        f"use null when a field is absent):\n{_BILL_SCHEMA}\n\n"
        "Rules: taxable_base is the amount BEFORE tax. total_gst = cgst+sgst+igst "
        "if those are given. Do not confuse quantities/HSN codes with money.\n\n"
        f"BILL TEXT:\n{text[:5000]}",
        system="You are a precise invoice data-extraction engine. Output only JSON, no prose, no markdown fences.",
        max_tokens=900,
    )
    if not out:
        return None
    import json
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2. Expense categorization
# ---------------------------------------------------------------------------
_CATEGORY_RULES = [
    (r"rent|lease|office space", "6100", "Rent"),
    (r"salary|payroll|wage", "6200", "Salaries"),
    (r"aws|azure|gcp|cloud|saas|software|subscription", "6000", "Software/Cloud"),
    (r"travel|flight|uber|ola|taxi|hotel", "6000", "Travel"),
    (r"electricity|power|water|internet|utility", "6000", "Utilities"),
    (r"raw material|inventory|stock|goods", "1200", "Inventory"),
    (r"machine|equipment|laptop|furniture|asset", "1500", "Fixed Asset"),
]


def categorize_expense(description: str, amount: float | None = None) -> dict:
    desc = (description or "").lower()
    for pattern, code, label in _CATEGORY_RULES:
        if re.search(pattern, desc):
            return {"account_code": code, "category": label,
                    "confidence": 0.8, "engine": "rules"}
    return {"account_code": "6000", "category": "General Expense",
            "confidence": 0.4, "engine": "rules"}


# ---------------------------------------------------------------------------
# 3. Fraud detection
# ---------------------------------------------------------------------------
def score_fraud(
    db: Session, org_id: int, *, amount: float, when: date | None = None,
    vendor_id: int | None = None, description: str = "",
) -> dict:
    when = when or date.today()
    reasons: list[str] = []
    score = 0.0

    if float(amount) == round(float(amount)) and float(amount) % 1000 == 0 and amount >= 10000:
        reasons.append("Round amount >= 10,000 (possible fabricated figure)")
        score += 0.25
    if when.weekday() >= 5:
        reasons.append("Transaction dated on a weekend")
        score += 0.2
    # Duplicate: same vendor + same amount within 7 days
    if vendor_id is not None:
        recent = db.scalars(
            select(Invoice).where(
                Invoice.org_id == org_id, Invoice.vendor_id == vendor_id,
                Invoice.total == money(amount),
                Invoice.issue_date >= when - timedelta(days=7),
            )
        ).all()
        if recent:
            reasons.append(f"Duplicate: {len(recent)} matching bill(s) in last 7 days")
            score += 0.4
    if amount >= 100000:
        reasons.append("High-value transaction (>= 1,00,000) — review recommended")
        score += 0.15

    score = min(score, 1.0)
    level = "high" if score >= 0.6 else "medium" if score >= 0.3 else "low"
    return {"risk_score": round(score, 2), "risk_level": level,
            "reasons": reasons or ["No anomalies detected"], "engine": "rules"}


# ---------------------------------------------------------------------------
# 4. Cashflow forecast
# ---------------------------------------------------------------------------
def forecast_cashflow(db: Session, org_id: int, horizon_days: int = 90) -> dict:
    """Project cash using current balance + expected AR inflows - AP outflows,
    scheduled by due date, with a moving-average smoothing on unknowns."""
    k = dashboard.kpis(db, org_id)
    start_cash = Decimal(str(k["cash_balance"]))
    today = date.today()

    ar = db.execute(
        select(Invoice.total, Invoice.amount_paid, Invoice.due_date).where(
            Invoice.org_id == org_id, Invoice.kind == "AR",
            Invoice.status.in_(("open", "partial")),
        )
    ).all()
    ap = db.execute(
        select(Invoice.total, Invoice.amount_paid, Invoice.due_date).where(
            Invoice.org_id == org_id, Invoice.kind == "AP",
            Invoice.status.in_(("open", "partial")),
        )
    ).all()

    points = []
    running = start_cash
    for d in range(0, horizon_days + 1, 7):
        day = today + timedelta(days=d)
        inflow = sum((money(t) - money(p) for t, p, due in ar if due <= day), Decimal("0"))
        outflow = sum((money(t) - money(p) for t, p, due in ap if due <= day), Decimal("0"))
        projected = start_cash + inflow - outflow
        points.append({"date": day.isoformat(), "projected_cash": float(money(projected))})
        running = projected

    low = min(points, key=lambda p: p["projected_cash"])
    return {
        "horizon_days": horizon_days,
        "start_cash": float(money(start_cash)),
        "end_cash": points[-1]["projected_cash"],
        "lowest_point": low,
        "series": points,
        "engine": "aging-model",
    }


# ---------------------------------------------------------------------------
# 5. Finance chatbot (grounded)
# ---------------------------------------------------------------------------
def chat(db: Session, org_id: int, question: str) -> dict:
    q = (question or "").lower()
    k = dashboard.kpis(db, org_id)

    def fmt(v):
        return f"₹{v:,.2f}"

    facts = {
        "cash": f"Current cash & bank balance is {fmt(k['cash_balance'])}.",
        "receivable": f"Total receivables (money owed to you) is {fmt(k['receivables'])}.",
        "payable": f"Total payables (money you owe) is {fmt(k['payables'])}.",
        "gst": f"Net GST due is {fmt(k['gst_due'])}.",
        "profit": f"Profit is {fmt(k['profit'])} (revenue {fmt(k['revenue'])} − expenses {fmt(k['expenses'])}).",
        "revenue": f"Total revenue booked is {fmt(k['revenue'])}.",
        "expense": f"Total expenses booked is {fmt(k['expenses'])}.",
    }

    # Intent match (deterministic, always correct against live data)
    triggers = {
        "cash": ["cash", "balance", "bank"],
        "receivable": ["receivable", "owed to", "collect", "debtor"],
        "payable": ["payable", "we owe", "creditor", "pay"],
        "gst": ["gst", "tax due"],
        "profit": ["profit", "p&l", "pnl", "loss", "net income"],
        "revenue": ["revenue", "sales", "income", "turnover"],
        "expense": ["expense", "spend", "cost"],
    }
    matched = [key for key, words in triggers.items() if any(w in q for w in words)]
    grounded = " ".join(facts[m] for m in matched) if matched else ""

    # If an LLM is configured, let it phrase the answer using grounded facts.
    if active_provider() != "rules":
        context = "; ".join(facts.values())
        llm = complete(
            f"Question: {question}\n\nAuthoritative live figures: {context}\n\n"
            "Answer the question using ONLY these figures. Be concise.",
            system="You are an ERP finance assistant. Never invent numbers.",
        )
        if llm:
            return {"answer": llm, "engine": active_provider(), "grounded_on": matched}

    if grounded:
        return {"answer": grounded, "engine": "rules", "grounded_on": matched}
    return {
        "answer": ("I can answer questions about cash, receivables, payables, GST, "
                   "revenue, expenses, and profit. Try: \"What is my cash balance?\""),
        "engine": "rules", "grounded_on": [],
    }
