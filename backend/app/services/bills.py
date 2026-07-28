"""Bill ingestion & distribution.

Captures a vendor bill from manual entry, PDF, Excel, or CSV, then distributes
its total across GL sections (Expense / GST Input / TDS / Accounts Payable) and
posts a single balanced journal entry.

Accounting split for a bill:
    Dr Expense          (base)
    Dr GST Input Credit (gst)
        Cr TDS Payable      (tds)
        Cr Accounts Payable (net = base + gst - tds)
Debits (base+gst) == Credits (tds + net), so it is always balanced.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import skills
from app.models.invoice import Invoice, InvoiceLine
from app.models.org import Organization
from app.models.party import Vendor
from app.services import accounts as acct
from app.services import gst as gst_mod
from app.services import tax_rules
from app.services.ledger import LineInput, money, post_entry, PostingError

ZERO = Decimal("0")
_GSTIN_RE = gst_mod.GSTIN_RE  # shared shape regex — see gst.pick_vendor_gstin
_VENDOR_LABEL = re.compile(
    r"(?:vendor|supplier|seller|billed by|sold by|bill from|company name|m/s)\s*[:\-]?\s*(.*)",
    re.I,
)
# A line that starts the buyer/recipient block — its name must never be
# mistaken for the vendor's (see extract_vendor's fallback name scan).
_BUYER_LABEL_LINE = re.compile(
    r"^\s*(?:bill\s*to|ship\s*to|buyer|recipient|consignee|customer|billed\s*to|"
    r"delivered\s*to|purchaser)\b",
    re.I,
)

def _num(s: str) -> Decimal:
    if not s:
        return ZERO
    s = re.sub(r"(?i)[₹$]|rs\.?|inr|/-|,|\s", "", s)
    return money(s) if s else ZERO


# A numeric token that is NOT a percentage (skip "9%", "18 %", etc.).
_TOKEN_RE = re.compile(r"(?<![\d.])(\d[\d,]*\.?\d*)\b")


def _line_amount(line: str) -> Decimal | None:
    """Rightmost money value on a line, ignoring percentages and small counts."""
    amounts: list[Decimal] = []
    for m in _TOKEN_RE.finditer(line):
        after = line[m.end():m.end() + 3].lstrip()
        if after.startswith("%"):
            continue  # a rate, not an amount
        amounts.append(_num(m.group(1)))
    # The amount column is the rightmost figure on the line.
    return amounts[-1] if amounts else None


# Lines whose "total" is a count/measure, not money (must never be the invoice total).
_QTY_LINE = re.compile(
    r"qty|quantit|\bitems?\b|\bpcs\b|\bnos\b|\bunits?\b|in words|weight|\bkg\b|hsn|sac|\bno\.?\b",
    re.I,
)


def extract_amounts(text: str) -> dict:
    """Line-based labelled-amount extraction. Robust to values sharing a line
    with rates (e.g. 'CGST @ 9% : 7,740.00'), split CGST/SGST/IGST, and 'Total
    Qty' / 'Total Items' lines that must not be mistaken for the invoice total."""
    base = gst_direct = tds = net = None
    cgst = sgst = igst = ZERO
    total_candidates: list[tuple[int, Decimal]] = []  # (priority, amount)

    for raw in text.splitlines():
        low = raw.lower()
        if not any(c.isdigit() for c in raw):
            continue
        amt = _line_amount(raw)
        if amt is None:
            continue
        if "gstin" in low or "uin" in low:
            continue  # GST *number*, not an amount
        if re.search(r"taxable|sub[\s-]?total|basic|amount before tax", low) and not _QTY_LINE.search(low):
            base = amt
        elif "cgst" in low:
            cgst = amt
        elif "sgst" in low or "utgst" in low:
            sgst = amt
        elif "igst" in low:
            igst = amt
        elif re.search(r"(?:total gst|gst amount|total tax|tax amount|\bgst\b)", low):
            gst_direct = amt
        elif re.search(r"\btds\b|t\.d\.s|tax deducted|withholding", low):
            tds = amt
        elif re.search(r"net (?:amount )?payable|balance payable|amount due", low):
            net = amt
        elif not _QTY_LINE.search(low):
            # Total, ranked by label specificity; qty/count lines are excluded.
            if re.search(r"grand total|invoice total|total invoice|total payable|amount payable", low):
                total_candidates.append((3, amt))
            elif re.search(r"total amount|bill total|total value", low):
                total_candidates.append((2, amt))
            elif re.search(r"\btotal\b", low):
                total_candidates.append((1, amt))

    gst = gst_direct if gst_direct is not None else money(cgst + sgst + igst)

    # Pick the most specific total; among equals, the largest figure.
    total = None
    if total_candidates:
        best = max(p for p, _ in total_candidates)
        total = max(a for p, a in total_candidates if p == best)

    # Reconcile any missing figure (gross = base + gst).
    warnings: list[str] = []
    if base is None and total is not None:
        base = money(total - gst)  # total treated as gross (pre-TDS)
    if total is None and base is not None:
        total = money(base + gst)
    base = base if base is not None else ZERO
    gst = gst if gst is not None else ZERO
    tds = tds if tds is not None else ZERO
    total = total if total is not None else money(base + gst)

    # Sanity checks -> surfaced to the user for review.
    if base and money(base + gst) != money(total):
        warnings.append(f"Base + GST ({money(base + gst)}) != stated total ({money(total)}).")
    if net is not None and money(base + gst - tds) != money(net):
        warnings.append(f"Computed net payable ({money(base + gst - tds)}) != stated ({money(net)}).")
    if not base:
        warnings.append("Could not detect a taxable/base amount — please enter it manually.")

    confidence = 0.9 if base and gst and not warnings else 0.6 if base else 0.2
    return {
        "base": float(money(base)), "gst": float(money(gst)), "tds": float(money(tds)),
        "gross": float(money(total)), "net": float(money(net)) if net is not None else None,
        "cgst": float(money(cgst)), "sgst": float(money(sgst)), "igst": float(money(igst)),
        "warnings": warnings, "confidence": confidence,
    }


def extract_vendor(text: str, *, own_gstin: str | None = None) -> tuple[str | None, str | None, list[str]]:
    """Best-effort vendor name + GSTIN from bill text.

    A tax invoice legally shows both parties' GSTINs (seller + registered
    buyer) — see gst.pick_vendor_gstin for how the seller's is disambiguated
    rather than just taking whichever GSTIN appears first.
    """
    text = text or ""
    gstin, gstin_warnings = gst_mod.pick_vendor_gstin(text, own_gstin=own_gstin)

    lines = text.splitlines()
    name = None

    # 1) A seller/vendor label — value inline, or on the next non-blank line
    #    (common "Sold By:\nAcme Pvt Ltd" layout, incl. after OCR line-splitting).
    for i, line in enumerate(lines):
        m = _VENDOR_LABEL.search(line)
        if not m:
            continue
        cand = m.group(1).strip(" :-\t")
        if not cand:
            for nxt in lines[i + 1:i + 3]:
                nxt = nxt.strip()
                if nxt:
                    cand = nxt
                    break
        if cand and "gstin" not in cand.lower() and len(cand) >= 3:
            name = cand[:120]
            break

    if not name:
        # 2) Fallback: first plausible line near the top — but skip a buyer/
        #    recipient block entirely, or we'd grab their name instead.
        skip_until = -1
        for i, line in enumerate(lines[:12]):
            s = line.strip()
            low = s.lower()
            if _BUYER_LABEL_LINE.search(s):
                skip_until = i + 2  # this label line + up to 2 following lines
                continue
            if i <= skip_until:
                continue
            if len(s) < 3 or _GSTIN_RE.search(s):
                continue
            if re.search(r"tax invoice|^invoice|^bill|^gstin|^date|^ref|^po\b|^order", low):
                continue
            if sum(c.isdigit() for c in s) > len(s) * 0.4:
                continue
            name = s[:120]
            break
    return name, gstin, gstin_warnings


def resolve_vendor(
    db: Session, org_id: int, *, vendor_id: int | None = None,
    name: str | None = None, gstin: str | None = None,
) -> tuple[Vendor | None, bool]:
    """Find an existing vendor (by id, GSTIN, then name) or create a new one.
    Returns (vendor, created)."""
    if vendor_id:
        v = db.get(Vendor, vendor_id)
        if v and v.org_id == org_id:
            return v, False
    gstin = (gstin or "").strip() or None
    name = (name or "").strip() or None
    if gstin:
        v = db.scalar(select(Vendor).where(Vendor.org_id == org_id, Vendor.gstin == gstin))
        if v:
            return v, False
    if name:
        v = db.scalar(
            select(Vendor).where(Vendor.org_id == org_id, func.lower(Vendor.name) == name.lower())
        )
        if v:
            return v, False
    if name or gstin:
        v = Vendor(org_id=org_id, name=name or gstin, gstin=gstin, ai_score=50)
        db.add(v)
        db.flush()
        return v, True
    return None, False


@dataclass
class Distribution:
    base: Decimal = ZERO
    gst: Decimal = ZERO
    gst_rate: Decimal = ZERO
    gst_split: gst_mod.GstSplit = field(default_factory=gst_mod.GstSplit)
    tds: Decimal = ZERO
    tds_rate: Decimal = ZERO
    expense_account_code: str = "6000"
    expense_category: str = "General Expense"
    sections: list[dict] = field(default_factory=list)

    @property
    def gross(self) -> Decimal:
        return money(self.base + self.gst)

    @property
    def net_payable(self) -> Decimal:
        return money(self.gross - self.tds)

    @property
    def balanced(self) -> bool:
        debit = self.base + self.gst
        credit = self.tds + self.net_payable
        return money(debit) == money(credit)

    def to_dict(self) -> dict:
        return {
            "base": float(money(self.base)),
            "gst": float(money(self.gst)),
            "gst_rate": float(money(self.gst_rate)),
            "gst_split": self.gst_split.to_dict(),
            "tds": float(money(self.tds)),
            "tds_rate": float(money(self.tds_rate)),
            "gross": float(self.gross),
            "net_payable": float(self.net_payable),
            "expense_account_code": self.expense_account_code,
            "expense_category": self.expense_category,
            "sections": self.sections,
            "balanced": self.balanced,
        }


def distribute(
    *,
    base: float | None = None,
    gross: float | None = None,
    gst_rate: float | None = None,
    gst_amount: float | None = None,
    tds_rate: float | None = None,
    tds_amount: float | None = None,
    description: str = "",
    org_state: str | None = None,
    vendor_state: str | None = None,
) -> Distribution:
    """Compute the section split, inferring whatever wasn't provided."""
    d = Distribution()
    grate = money(gst_rate) if gst_rate is not None else ZERO

    if base is not None:
        d.base = money(base)
        d.gst = money(gst_amount) if gst_amount is not None else money(d.base * grate / 100)
    elif gross is not None:
        g = money(gross)
        if gst_amount is not None:
            d.gst = money(gst_amount)
            d.base = money(g - d.gst)
        elif grate > 0:
            d.base = money(g / (1 + grate / 100))
            d.gst = money(g - d.base)
        else:
            d.base = g
            d.gst = ZERO
    else:
        raise PostingError("Provide either a base amount or a gross total.")

    d.gst_rate = money(d.gst / d.base * 100) if d.base else ZERO
    d.gst_split = gst_mod.split_gst(d.gst, org_state, vendor_state)

    d.tds_rate = money(tds_rate) if tds_rate is not None else ZERO
    d.tds = money(tds_amount) if tds_amount is not None else money(d.base * d.tds_rate / 100)

    # AI-categorize the expense account from the description.
    cat = skills.categorize_expense(description)
    d.expense_account_code = cat["account_code"]
    d.expense_category = cat["category"]

    d.sections = [
        {"section": d.expense_category, "account_code": d.expense_account_code,
         "side": "debit", "amount": float(money(d.base))},
        *gst_mod.gst_line_sections(d.gst_split, direction="input"),
        {"section": "TDS Payable", "account_code": "2110",
         "side": "credit", "amount": float(money(d.tds))},
        {"section": "Accounts Payable", "account_code": "2000",
         "side": "credit", "amount": float(d.net_payable)},
    ]
    return d


# ---------------------------------------------------------------------------
# File parsing — any file type routed through the universal extractor
# ---------------------------------------------------------------------------
def parse_bill(filename: str, content: bytes, *, own_gstin: str | None = None) -> dict:
    """Extract text (via any-format extractor incl. OCR) + amounts from a bill."""
    from app.services.extract import extract

    try:
        text, mode, ocr_used = extract(filename, content)
    except Exception as e:
        return {
            "entry_mode": "manual", "invoice_number": None, "invoice_date": None,
            "vendor_gstin": None, "base": 0.0, "gross": 0.0, "gst": 0.0, "tds": 0.0,
            "net": None, "cgst": 0.0, "sgst": 0.0, "igst": 0.0,
            "confidence": 0.0, "engine": "rules", "ocr_used": False,
            "warnings": [f"Could not read this file ({e}). Enter the amounts manually."],
            "text_preview": "",
        }

    if not text.strip():
        return {
            "entry_mode": mode, "invoice_number": None, "invoice_date": None,
            "vendor_gstin": None, "base": 0.0, "gross": 0.0, "gst": 0.0, "tds": 0.0,
            "net": None, "cgst": 0.0, "sgst": 0.0, "igst": 0.0,
            "confidence": 0.0, "engine": "rules", "ocr_used": ocr_used,
            "warnings": ["No readable text found in this file — enter the amounts manually."],
            "text_preview": "",
        }

    extracted = skills.read_invoice(text, own_gstin=own_gstin)
    amt = extract_amounts(text)
    vendor_name, vendor_gstin, gstin_warnings = extract_vendor(text, own_gstin=own_gstin)
    warnings = list(amt["warnings"]) + gstin_warnings
    if ocr_used:
        warnings.insert(0, "Read via OCR (scanned/image) — please double-check the amounts.")

    # Start from the rule-based figures.
    result = {
        "entry_mode": mode,
        "ocr_used": ocr_used,
        "engine": "rules",
        "invoice_number": extracted.get("invoice_number"),
        "invoice_date": extracted.get("invoice_date"),
        "vendor_name": vendor_name,
        "vendor_gstin": vendor_gstin or extracted.get("vendor_gstin"),
        "base": amt["base"], "gross": amt["gross"], "gst": amt["gst"],
        "tds": amt["tds"], "net": amt["net"],
        "cgst": amt["cgst"], "sgst": amt["sgst"], "igst": amt["igst"],
        "confidence": amt["confidence"],
        "line_items": [],
        "warnings": warnings,
        "text_preview": text[:1200],
    }

    # If an LLM is configured, prefer its structured extraction (far more accurate
    # on arbitrary layouts); keep rule figures for anything it leaves null.
    llm = skills.llm_extract_bill(text, own_gstin=own_gstin)
    if llm:
        def num(v):
            try:
                return None if v is None else float(str(v).replace(",", ""))
            except (TypeError, ValueError):
                return None
        gst = num(llm.get("total_gst"))
        parts = [num(llm.get(k)) or 0 for k in ("cgst", "sgst", "igst")]
        if gst is None and any(parts):
            gst = sum(parts)
        merged = {
            "base": num(llm.get("taxable_base")),
            "gst": gst,
            "tds": num(llm.get("tds")),
            "gross": num(llm.get("grand_total")),
            "net": num(llm.get("net_payable")),
            "cgst": num(llm.get("cgst")), "sgst": num(llm.get("sgst")),
            "igst": num(llm.get("igst")),
        }
        for k, v in merged.items():
            if v is not None:
                result[k] = v
        if llm.get("vendor_name"):
            result["vendor_name"] = llm["vendor_name"]
        llm_gstin = (llm.get("vendor_gstin") or "").strip().upper() or None
        if llm_gstin and own_gstin and llm_gstin == own_gstin.strip().upper():
            result["warnings"].append(
                "AI extraction returned our own GSTIN as the vendor's — ignored; "
                "kept the rule-based match instead."
            )
        elif llm_gstin:
            result["vendor_gstin"] = llm["vendor_gstin"]
        if llm.get("invoice_number"):
            result["invoice_number"] = llm["invoice_number"]
        if llm.get("invoice_date"):
            result["invoice_date"] = llm["invoice_date"]
        items = llm.get("line_items") or []
        result["line_items"] = [
            {"description": str(it.get("description", "")).strip(),
             "amount": num(it.get("amount")) or 0}
            for it in items if isinstance(it, dict) and it.get("description")
        ]
        result["engine"] = "ai"
        result["confidence"] = 0.95
    else:
        from app.ai.provider import active_provider
        if active_provider() != "rules":
            result["warnings"].append(
                "AI extraction is configured but the call failed (commonly an API "
                "quota/billing issue) — used rule-based reading instead."
            )

    return result


# ---------------------------------------------------------------------------
# Itemised classification & distribution (tax rules by item)
# ---------------------------------------------------------------------------
def classify_bill_items(items: list[dict], *, tds_rate: float = 0,
                        tds_amount: float | None = None,
                        org_state: str | None = None, vendor_state: str | None = None) -> dict:
    """Classify each line item (pen, book, laptop…) into a category with its
    applicable GST rate + GL account, compute per-item GST, and group by account
    for posting. `items` = [{description, amount}] (amount = taxable value)."""
    lines = []
    groups: dict[str, dict] = {}   # account_code -> {category, base, gst}
    subtotal = ZERO
    gst_total = ZERO

    for it in items:
        desc = (it.get("description") or "").strip()
        amt = money(it.get("amount") or 0)
        if amt <= 0:
            continue
        rule = tax_rules.classify_item(desc)
        rate = money(rule["gst_rate"])
        gst = money(amt * rate / 100)
        subtotal += amt
        gst_total += gst
        lines.append({
            "description": desc, "amount": float(amt),
            "category": rule["category"], "hsn": rule["hsn"],
            "gst_rate": float(rate), "gst_amount": float(gst),
            "account_code": rule["account_code"], "account_name": rule["account_name"],
        })
        g = groups.setdefault(rule["account_code"], {
            "category": rule["category"], "account_name": rule["account_name"],
            "base": ZERO, "gst": ZERO,
        })
        g["base"] += amt
        g["gst"] += gst

    subtotal = money(subtotal)
    gst_total = money(gst_total)
    gst_split = gst_mod.split_gst(gst_total, org_state, vendor_state)
    tds = money(tds_amount) if tds_amount is not None else money(subtotal * money(tds_rate) / 100)
    net_payable = money(subtotal + gst_total - tds)

    # Build the section preview (per-category expense lines + GST + TDS + AP).
    sections = []
    for code, g in groups.items():
        sections.append({"section": g["category"], "account_code": code,
                         "side": "debit", "amount": float(money(g["base"]))})
    sections.extend(gst_mod.gst_line_sections(gst_split, direction="input"))
    if tds > 0:
        sections.append({"section": "TDS Payable", "account_code": "2110",
                         "side": "credit", "amount": float(tds)})
    sections.append({"section": "Accounts Payable", "account_code": "2000",
                     "side": "credit", "amount": float(net_payable)})

    return {
        "lines": lines,
        "groups": {k: {"category": v["category"], "account_name": v["account_name"],
                       "base": float(money(v["base"])), "gst": float(money(v["gst"]))}
                   for k, v in groups.items()},
        "subtotal": float(subtotal), "gst_total": float(gst_total), "gst_split": gst_split.to_dict(),
        "tds": float(tds), "net_payable": float(net_payable),
        "sections": sections,
        "balanced": True,
    }


def post_bill_items(
    db: Session, *, org_id: int, vendor_id: int | None, number: str,
    issue_date: date, due_date: date, entry_mode: str,
    items: list[dict], tds_rate: float = 0, tds_amount: float | None = None,
    vendor_name: str | None = None, vendor_gstin: str | None = None,
) -> tuple[Invoice, Vendor | None, bool, dict]:
    """Post an itemised bill: one expense line per tax category, GST input, TDS,
    and net payable — all in a single balanced journal entry."""
    result = classify_bill_items(items, tds_rate=tds_rate, tds_amount=tds_amount)
    if money(result["subtotal"]) <= 0:
        raise PostingError("Bill must have at least one item with a positive amount.")

    vendor, created = resolve_vendor(
        db, org_id, vendor_id=vendor_id, name=vendor_name, gstin=vendor_gstin
    )

    # Recompute the authoritative CGST/SGST/IGST split now that the vendor is
    # resolved — never trust whatever state info the pre-posting preview had.
    org_row = db.get(Organization, org_id)
    own_state = gst_mod.resolve_state(org_row.state_code if org_row else None,
                                       org_row.gstin if org_row else None)
    cp_state = gst_mod.resolve_state(vendor.state_code if vendor else None,
                                      vendor.gstin if vendor else None)
    gst_split = gst_mod.split_gst(money(result["gst_total"]), own_state, cp_state)

    lines: list[LineInput] = []
    for code, g in result["groups"].items():
        acc = acct.by_code(db, org_id, code)
        if acc is None:
            acc = acct.std(db, org_id, "opex")  # fall back to general expenses
        lines.append(LineInput(acc.id, debit=money(g["base"]),
                               description=f"{g['category']} — {number}"))
    for row in gst_mod.gst_line_sections(gst_split, direction="input"):
        lines.append(LineInput(acct.by_code(db, org_id, row["account_code"]).id,
                               debit=money(row["amount"]), description=row["section"]))
    if money(result["tds"]) > 0:
        lines.append(LineInput(acct.std(db, org_id, "tds_payable").id,
                               credit=money(result["tds"]), description="TDS withheld"))
    lines.append(LineInput(acct.std(db, org_id, "ap").id,
                           credit=money(result["net_payable"]), description=f"Payable {number}"))

    entry = post_entry(
        db, org_id=org_id, entry_date=issue_date,
        memo=f"AP bill {number} ({entry_mode}, itemised)", lines=lines,
        source="invoice", ref=number,
    )

    inv = Invoice(
        org_id=org_id, kind="AP", number=number,
        vendor_id=vendor.id if vendor else None,
        issue_date=issue_date, due_date=due_date,
        subtotal=float(money(result["subtotal"])), tax_total=float(money(result["gst_total"])),
        tds_total=float(money(result["tds"])), total=float(money(result["net_payable"])),
        status="open", entry_mode=entry_mode, journal_entry_id=entry.id,
        ai_meta=json.dumps({"gst": gst_split.to_dict()}),
    )
    for item_line in result["lines"]:
        acc = acct.by_code(db, org_id, item_line["account_code"])
        inv.lines.append(InvoiceLine(
            description=item_line["description"], quantity=1,
            unit_price=item_line["amount"], tax_rate=item_line["gst_rate"],
            hsn_sac=item_line["hsn"], account_id=acc.id if acc else None,
        ))
    db.add(inv)
    db.flush()
    return inv, vendor, created, result


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------
def post_bill(
    db: Session, *, org_id: int, vendor_id: int | None, number: str,
    issue_date: date, due_date: date, entry_mode: str, dist: Distribution,
    description: str = "", vendor_name: str | None = None,
    vendor_gstin: str | None = None,
) -> tuple[Invoice, Vendor | None, bool]:
    """Create an AP bill and post the multi-section distribution journal.

    Auto-captures the vendor: if no existing vendor is matched (by id, GSTIN, or
    name), a new vendor account is created. Returns (invoice, vendor, created)."""
    if dist.base <= 0:
        raise PostingError("Bill base amount must be positive.")

    vendor, created = resolve_vendor(
        db, org_id, vendor_id=vendor_id, name=vendor_name, gstin=vendor_gstin
    )
    vendor_id = vendor.id if vendor else None

    # Recompute the authoritative CGST/SGST/IGST split now that the vendor is
    # resolved — never trust whatever state info the pre-posting preview had.
    org_row = db.get(Organization, org_id)
    own_state = gst_mod.resolve_state(org_row.state_code if org_row else None,
                                       org_row.gstin if org_row else None)
    cp_state = gst_mod.resolve_state(vendor.state_code if vendor else None,
                                      vendor.gstin if vendor else None)
    dist.gst_split = gst_mod.split_gst(dist.gst, own_state, cp_state)

    lines = [
        LineInput(acct.by_code(db, org_id, dist.expense_account_code).id,
                  debit=dist.base, description=description or f"Expense {number}"),
    ]
    for row in gst_mod.gst_line_sections(dist.gst_split, direction="input"):
        lines.append(LineInput(acct.by_code(db, org_id, row["account_code"]).id,
                               debit=money(row["amount"]), description=row["section"]))
    if dist.tds > 0:
        lines.append(LineInput(acct.std(db, org_id, "tds_payable").id,
                               credit=dist.tds, description="TDS withheld"))
    lines.append(LineInput(acct.std(db, org_id, "ap").id,
                           credit=dist.net_payable, description=f"Payable {number}"))

    entry = post_entry(
        db, org_id=org_id, entry_date=issue_date,
        memo=f"AP bill {number} ({entry_mode})", lines=lines,
        source="invoice", ref=number,
    )

    inv = Invoice(
        org_id=org_id, kind="AP", number=number, vendor_id=vendor_id,
        issue_date=issue_date, due_date=due_date,
        subtotal=float(money(dist.base)), tax_total=float(money(dist.gst)),
        tds_total=float(money(dist.tds)), total=float(dist.net_payable),
        status="open", entry_mode=entry_mode, journal_entry_id=entry.id,
        ai_meta=json.dumps({"gst": dist.gst_split.to_dict()}),
    )
    db.add(inv)
    db.flush()
    return inv, vendor, created
