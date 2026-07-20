"""Tax-rules engine: classify a bill line item by its description into a
category with the applicable Indian GST rate (HSN/SAC based) and a GL account.

Rates below are the standard GST slabs for each category. They are intentionally
data-driven so they can be tuned / made org-configurable later. Order matters —
more specific rules come first (e.g. 'books' before generic 'stationery').
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TaxRule:
    category: str
    hsn: str          # representative HSN (goods) or SAC (services)
    gst_rate: float   # % GST
    account_code: str  # GL expense/asset account
    keywords: tuple[str, ...]


# --- The catalog (representative Indian GST slabs) -------------------------
RULES: list[TaxRule] = [
    TaxRule("Books & Printed Material", "4901", 0, "6300",
            ("book", "textbook", "printed book", "magazine", "periodical", "journal book")),
    TaxRule("Stationery", "4820", 12, "6300",
            ("pen", "pencil", "notebook", "note book", "register", "diary", "eraser",
             "sharpener", "marker", "highlighter", "stapler", "paper", "envelope",
             "file", "folder", "glue", "stationery", "stationary", "ink", "clip")),
    TaxRule("Software & Subscriptions", "997331", 18, "6400",
            ("software", "license", "licence", "subscription", "saas", "cloud",
             "hosting", "aws", "azure", "gcp", "domain", "api", "app")),
    TaxRule("Computers & IT Hardware", "8471", 18, "1500",
            ("laptop", "computer", "desktop", "cpu", "monitor", "server", "printer",
             "keyboard", "mouse", "hard disk", "ssd", "ram", "router", "scanner")),
    TaxRule("Mobile & Communication", "8517", 18, "1500",
            ("mobile", "smartphone", "phone", "tablet", "ipad")),
    TaxRule("Furniture & Fixtures", "9403", 18, "1500",
            ("chair", "table", "desk", "furniture", "cabinet", "sofa", "almirah", "shelf")),
    TaxRule("Electronics & Appliances", "8415", 18, "1500",
            ("air conditioner", " ac ", "refrigerator", "fridge", "television", " tv ",
             "projector", "camera", "ups", "inverter", "fan")),
    TaxRule("Rent (Commercial)", "997212", 18, "6100",
            ("rent", "lease", "office space", "premises")),
    TaxRule("Professional & Legal Fees", "998211", 18, "6700",
            ("consulting", "consultancy", "audit", "legal", "advisory", "retainer",
             "professional", "accounting", "attorney", "lawyer")),
    TaxRule("Travel & Conveyance", "996411", 18, "6500",
            ("flight", "air ticket", "airfare", "hotel", "taxi", "cab", "uber", "ola",
             "travel", "conveyance", "lodging", "boarding")),
    TaxRule("Food & Refreshments", "9963", 5, "6000",
            ("food", "restaurant", "catering", "meal", "refreshment", "snack", "tea", "coffee")),
    TaxRule("Utilities", "9969", 18, "6600",
            ("electricity", "power bill", "water", "gas", "internet", "broadband",
             "telephone", "utility", "wifi")),
    TaxRule("Freight & Logistics", "9965", 18, "6900",
            ("freight", "courier", "logistics", "transport", "shipping", "cargo", "delivery")),
    TaxRule("Repairs & Maintenance", "9987", 18, "6800",
            ("repair", "maintenance", "amc", "servicing", "spare part")),
    TaxRule("Raw Material / Metal", "7214", 18, "1200",
            ("steel", "iron", "tmt", "metal", "cement", "raw material", "rod", "wire", "aluminium")),
    TaxRule("Textiles & Apparel", "5208", 5, "1200",
            ("cloth", "fabric", "apparel", "garment", "textile", "uniform", "yarn")),
    TaxRule("Medicines & Pharma", "3004", 12, "6000",
            ("medicine", "drug", "pharma", "tablet", "syrup", "medical")),
]

# Fallback when nothing matches — general expense at the standard 18% slab.
DEFAULT_RULE = TaxRule("General Expense", "-", 18, "6000", ())

ACCOUNT_NAMES = {
    "1200": "Inventory", "1500": "Fixed Assets", "5000": "Cost of Goods Sold",
    "6000": "Operating Expenses", "6100": "Rent", "6300": "Stationery & Printing",
    "6400": "IT, Software & Subscriptions", "6500": "Travel & Conveyance",
    "6600": "Utilities", "6700": "Professional & Legal Fees",
    "6800": "Repairs & Maintenance", "6900": "Freight & Logistics",
}


def classify_item(description: str) -> dict:
    """Classify one line item -> category, HSN, GST rate, GL account."""
    text = f" {(description or '').lower()} "
    for rule in RULES:
        for kw in rule.keywords:
            # Whole-word match, tolerating a plural 's' ("pen"→"pens",
            # "textbook"→"textbooks") but not substrings ("pen"≠"pending").
            pat = re.escape(kw.strip())
            if re.search(rf"(?<![a-z]){pat}s?(?![a-z])", text):
                return _as_dict(rule, matched=kw.strip())
    return _as_dict(DEFAULT_RULE, matched=None)


def _as_dict(rule: TaxRule, matched: str | None) -> dict:
    return {
        "category": rule.category,
        "hsn": rule.hsn,
        "gst_rate": rule.gst_rate,
        "account_code": rule.account_code,
        "account_name": ACCOUNT_NAMES.get(rule.account_code, "Expense"),
        "matched_keyword": matched,
    }
