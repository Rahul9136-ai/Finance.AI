"""Indian GST place-of-supply determination and CGST/SGST/IGST split.

Scope & limitations (read before relying on this for a real filing):

This implements only the DEFAULT/general rule under the IGST Act: a supply
is intra-state (CGST + SGST) if the supplier's state and the place of supply
are the same state, and inter-state (IGST) otherwise (s.7/s.8 IGST Act). We
approximate "place of supply" as the counterparty's registered state (from
their GSTIN, or an explicit state code) versus our own org's state — correct
for the common case of a registered B2B recipient, but this module does NOT
implement the statutory exceptions in IGST Act ss.10-13, e.g.:
  - services related to immovable property (place of supply = property's state)
  - event admission/organisation (place of supply = event's state)
  - goods transportation agency / passenger transport rules
  - SEZ supplies (zero-rated regardless of state — needs separate handling)
  - exports (zero-rated / LUT — needs separate handling)
  - unregistered B2C supplies over the e-invoicing threshold with special POS rules
Those categories need case-by-case review by a tax professional; do not
assume this module's output is correct for them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.services import accounts as acct
from app.services.ledger import money

ZERO = Decimal("0")

# Official 2-digit GST/Census state & UT codes — these are the first two
# digits of every GSTIN. Source: CBIC state code list (Census 2011 codes).
STATE_CODES: dict[str, str] = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman & Diu", "26": "Dadra & Nagar Haveli", "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]$")


def state_code_from_gstin(gstin: str | None) -> str | None:
    """The first 2 digits of a valid-shaped GSTIN are its state code."""
    if not gstin:
        return None
    g = gstin.strip().upper()
    if not _GSTIN_RE.match(g):
        return None
    code = g[:2]
    return code if code in STATE_CODES else None


def resolve_state(explicit_state_code: str | None, gstin: str | None) -> str | None:
    """An explicitly-set state code wins (needed for unregistered parties with
    no GSTIN); otherwise derive it from the GSTIN."""
    if explicit_state_code and explicit_state_code in STATE_CODES:
        return explicit_state_code
    return state_code_from_gstin(gstin)


# A tax invoice is legally required to show the SELLER's GSTIN and, when the
# recipient is registered, the BUYER's GSTIN too — so a document commonly has
# two (or more, e.g. a "place of supply" table). Naively taking the first
# GSTIN-shaped match in the text is a common source of a wrong vendor GSTIN:
# it's frequently the buyer's — sometimes literally our own org's.
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d])\b")
_GSTIN_TOKEN_RE = GSTIN_RE  # internal alias used below
_BUYER_CONTEXT_RE = re.compile(
    r"bill\s*to|ship\s*to|buyer|recipient|consignee|customer|billed\s*to|"
    r"delivered\s*to|your\s*gstin|purchaser", re.I,
)
_SELLER_CONTEXT_RE = re.compile(
    r"seller|vendor|supplier|billed\s*by|sold\s*by|bill\s*from|"
    r"m/s|gstin\s*of\s*supplier|supplier'?s?\s*gstin", re.I,
)


def pick_vendor_gstin(text: str, *, own_gstin: str | None = None) -> tuple[str | None, list[str]]:
    """Pick the SELLER's GSTIN out of a bill/invoice's raw text.

    Excludes our own org's GSTIN outright (it can only ever be the recipient
    on a purchase bill), then prefers a match near a seller/vendor label over
    one near a buyer/recipient label, then falls back to the first remaining
    match. Returns (gstin_or_None, warnings) — a warning is added whenever
    more than one distinct GSTIN was found, so the result gets a human check.
    """
    text = text or ""
    own = (own_gstin or "").strip().upper() or None
    candidates = [(m.group(1), m.start()) for m in _GSTIN_TOKEN_RE.finditer(text)]
    candidates = [(g, pos) for g, pos in candidates if g != own]
    if not candidates:
        return None, []

    def label(pos: int) -> str:
        window = text[max(0, pos - 60):pos]
        if _BUYER_CONTEXT_RE.search(window):
            return "buyer"
        if _SELLER_CONTEXT_RE.search(window):
            return "seller"
        return "unknown"

    labelled = [(g, label(pos)) for g, pos in candidates]
    seller_matches = [g for g, lbl in labelled if lbl == "seller"]
    non_buyer_matches = [g for g, lbl in labelled if lbl != "buyer"]

    if seller_matches:
        picked = seller_matches[0]
    elif non_buyer_matches:
        picked = non_buyer_matches[0]
    else:
        picked = candidates[0][0]  # everything left is buyer-labelled — best effort

    warnings = []
    distinct = sorted({g for g, _ in candidates})
    if len(distinct) > 1:
        warnings.append(
            f"Multiple GSTINs found on this document ({', '.join(distinct)}) — "
            f"picked {picked} as the vendor's. Please verify against the original."
        )
    return picked, warnings


@dataclass
class GstSplit:
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    igst: Decimal = ZERO
    unclassified: Decimal = ZERO
    determination: str = "unknown"  # "intra-state" | "inter-state" | "unknown"

    def to_dict(self) -> dict:
        return {
            "cgst": float(self.cgst), "sgst": float(self.sgst),
            "igst": float(self.igst), "unclassified": float(self.unclassified),
            "determination": self.determination,
        }


def split_gst(total_gst, own_state: str | None, counterparty_state: str | None) -> GstSplit:
    """Split a computed GST amount into CGST+SGST vs IGST using the default
    place-of-supply rule (see module docstring for what this does not cover).

    If either state is unknown, the amount is left `unclassified` rather than
    guessed — callers should post it to a suspense GST account and prompt for
    the missing state, never silently assume intra- or inter-state.
    """
    total_gst = money(total_gst)
    if total_gst <= 0:
        return GstSplit()
    if not own_state or not counterparty_state:
        return GstSplit(unclassified=total_gst, determination="unknown")
    if own_state == counterparty_state:
        cgst = money(total_gst / 2)
        sgst = money(total_gst - cgst)
        return GstSplit(cgst=cgst, sgst=sgst, determination="intra-state")
    return GstSplit(igst=total_gst, determination="inter-state")


def gst_line_sections(split: GstSplit, *, direction: str) -> list[dict]:
    """Render a GstSplit as ledger/preview line rows for either the "input"
    (AP — Dr GST Input Credit, an asset/ITC) or "output" (AR — Cr GST Output
    Payable, a liability) side."""
    if direction not in ("input", "output"):
        raise ValueError("direction must be 'input' or 'output'")
    side = "debit" if direction == "input" else "credit"
    label = "Input Credit" if direction == "input" else "Output Payable"
    rows = []
    for tax, amount in (("CGST", split.cgst), ("SGST", split.sgst), ("IGST", split.igst)):
        if amount > 0:
            rows.append({
                "section": f"{tax} {label}",
                "account_code": acct.STD[f"gst_{direction}_{tax.lower()}"],
                "side": side, "amount": float(amount),
            })
    if split.unclassified > 0:
        rows.append({
            "section": f"GST {label} (unclassified — set vendor/customer/org state)",
            "account_code": acct.STD[f"gst_{direction}"],
            "side": side, "amount": float(split.unclassified),
        })
    return rows
