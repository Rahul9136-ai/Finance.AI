"""GSTIN-capture correctness: a tax invoice legally carries both the seller's
and the registered buyer's GSTIN, so naively taking the first match is a
common source of a wrong vendor GSTIN. These tests pin the disambiguation
logic in services/gst.py and its use in bills.extract_vendor."""
from app.services import bills, gst


SELLER_GSTIN = "27BBBBB1111B1Z5"
BUYER_GSTIN = "27AAAAA0000A1Z5"

TWO_GSTIN_BILL = f"""TAX INVOICE
Seller: Steel Supplies Co
GSTIN: {SELLER_GSTIN}

Bill To: Demo Manufacturing Pvt Ltd
GSTIN: {BUYER_GSTIN}

Steel rods 100 units
Taxable Amount: 50,000.00
Total: 59,000.00
"""

# Buyer's GSTIN printed FIRST — the naive "first match" bug would pick this.
BUYER_FIRST_BILL = f"""TAX INVOICE
Bill To: Demo Manufacturing Pvt Ltd
GSTIN: {BUYER_GSTIN}

Sold By: Steel Supplies Co
GSTIN: {SELLER_GSTIN}

Total: 59,000.00
"""


def test_single_gstin_no_context_is_returned_as_is():
    gstin, warnings = gst.pick_vendor_gstin(f"Vendor GSTIN: {SELLER_GSTIN}\nTotal: 100")
    assert gstin == SELLER_GSTIN
    assert warnings == []


def test_two_gstins_picks_seller_labelled_one_even_when_buyer_is_first():
    gstin, warnings = gst.pick_vendor_gstin(BUYER_FIRST_BILL)
    assert gstin == SELLER_GSTIN
    assert len(warnings) == 1
    assert SELLER_GSTIN in warnings[0] and BUYER_GSTIN in warnings[0]


def test_two_gstins_excludes_own_org_gstin_even_without_labels():
    text = f"Some doc\n{BUYER_GSTIN}\nmore text\n{SELLER_GSTIN}\nend"
    gstin, warnings = gst.pick_vendor_gstin(text, own_gstin=BUYER_GSTIN)
    assert gstin == SELLER_GSTIN


def test_own_gstin_excluded_takes_priority_over_label_heuristics():
    # Even if OUR gstin happens to sit near a "seller" label by coincidence,
    # it must never be returned as the vendor's.
    text = f"Seller GSTIN: {BUYER_GSTIN}\nBuyer GSTIN: {SELLER_GSTIN}"
    gstin, _ = gst.pick_vendor_gstin(text, own_gstin=BUYER_GSTIN)
    assert gstin == SELLER_GSTIN


def test_no_gstin_in_text():
    assert gst.pick_vendor_gstin("no gst numbers here") == (None, [])


def test_bills_extract_vendor_picks_seller_not_buyer(text=TWO_GSTIN_BILL):
    name, gstin, warnings = bills.extract_vendor(text, own_gstin=BUYER_GSTIN)
    assert gstin == SELLER_GSTIN
    assert "Steel Supplies" in (name or "")


def test_bills_extract_vendor_buyer_first_layout_still_correct():
    name, gstin, warnings = bills.extract_vendor(BUYER_FIRST_BILL, own_gstin=BUYER_GSTIN)
    assert gstin == SELLER_GSTIN


def test_vendor_name_not_confused_with_buyer_name():
    # "Bill To" (buyer) appears before "Sold By" (seller), label value on the
    # NEXT line in both cases — the exact layout that broke this before.
    text = f"""TAX INVOICE

Bill To:
Demo Manufacturing Pvt Ltd
GSTIN: {BUYER_GSTIN}

Sold By:
Precision Tools Pvt Ltd
GSTIN: {SELLER_GSTIN}

Invoice No: INV-5555
Total: 29,500.00
"""
    name, gstin, warnings = bills.extract_vendor(text, own_gstin=BUYER_GSTIN)
    assert name == "Precision Tools Pvt Ltd"
    assert gstin == SELLER_GSTIN


def test_vendor_name_fallback_skips_buyer_block_with_no_seller_label():
    # No explicit "Sold By" label at all — fallback scan must still skip
    # past the whole buyer block rather than grabbing the buyer's name.
    text = f"""TAX INVOICE

Bill To:
Demo Manufacturing Pvt Ltd
GSTIN: {BUYER_GSTIN}

Precision Tools Pvt Ltd
GSTIN: {SELLER_GSTIN}

Invoice No: INV-5555
Total: 29,500.00
"""
    name, gstin, warnings = bills.extract_vendor(text, own_gstin=BUYER_GSTIN)
    assert name == "Precision Tools Pvt Ltd"


def test_parse_bill_end_to_end_picks_seller_gstin_when_own_gstin_known():
    # own_gstin excludes the buyer's outright, leaving one unambiguous
    # candidate — no "multiple GSTINs" warning needed in this case.
    result = bills.parse_bill("bill.txt", TWO_GSTIN_BILL.encode("utf-8"), own_gstin=BUYER_GSTIN)
    assert result["vendor_gstin"] == SELLER_GSTIN


def test_parse_bill_warns_on_ambiguity_when_own_gstin_unknown():
    result = bills.parse_bill("bill.txt", TWO_GSTIN_BILL.encode("utf-8"))
    assert result["vendor_gstin"] == SELLER_GSTIN  # still correct via seller label
    assert any("Multiple GSTINs" in w for w in result["warnings"])
