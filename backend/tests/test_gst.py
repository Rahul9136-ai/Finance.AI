"""Indian GST correctness tests: state-code derivation, the CGST/SGST-vs-IGST
place-of-supply split, and that real postings land in the correct split
ledger accounts (never guessed when a party's state is unknown)."""
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal

import pytest

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.invoice import Invoice, InvoiceLine  # noqa: E402
from app.models.org import Organization  # noqa: E402
from app.models.party import Customer, Vendor  # noqa: E402
from app.services import bills, dashboard, gst, invoicing  # noqa: E402
from app.services.ledger import account_balance  # noqa: E402


# ---------------------------------------------------------------------------
# Pure unit tests — no DB
# ---------------------------------------------------------------------------
def test_state_code_from_gstin_valid():
    assert gst.state_code_from_gstin("27AAAAA0000A1Z5") == "27"
    assert gst.state_code_from_gstin("29CCCCC2222C1Z5") == "29"


def test_state_code_from_gstin_invalid_or_missing():
    assert gst.state_code_from_gstin(None) is None
    assert gst.state_code_from_gstin("") is None
    assert gst.state_code_from_gstin("not-a-gstin") is None


def test_resolve_state_explicit_wins_over_gstin():
    assert gst.resolve_state("07", "27AAAAA0000A1Z5") == "07"


def test_resolve_state_falls_back_to_gstin():
    assert gst.resolve_state(None, "27AAAAA0000A1Z5") == "27"


def test_resolve_state_unknown_when_neither_available():
    assert gst.resolve_state(None, None) is None


def test_split_gst_intra_state_even():
    s = gst.split_gst(Decimal("1800"), "27", "27")
    assert s.determination == "intra-state"
    assert s.cgst == Decimal("900.00")
    assert s.sgst == Decimal("900.00")
    assert s.igst == Decimal("0.00")


def test_split_gst_intra_state_odd_paise_reconciles_exactly():
    s = gst.split_gst(Decimal("1801.11"), "27", "27")
    assert s.determination == "intra-state"
    assert s.cgst + s.sgst == Decimal("1801.11")  # must reconcile to the cent


def test_split_gst_inter_state():
    s = gst.split_gst(Decimal("1800"), "27", "29")
    assert s.determination == "inter-state"
    assert s.igst == Decimal("1800.00")
    assert s.cgst == Decimal("0.00") and s.sgst == Decimal("0.00")


def test_split_gst_unknown_state_is_unclassified_not_guessed():
    s = gst.split_gst(Decimal("1800"), None, "29")
    assert s.determination == "unknown"
    assert s.unclassified == Decimal("1800.00")
    assert s.cgst == 0 and s.sgst == 0 and s.igst == 0


def test_split_gst_zero_amount():
    s = gst.split_gst(Decimal("0"), "27", "27")
    assert s.cgst == 0 and s.sgst == 0 and s.igst == 0 and s.unclassified == 0


# ---------------------------------------------------------------------------
# Integration — real DB, real postings
# ---------------------------------------------------------------------------
COA = [
    ("1000", "Cash", "asset"), ("1010", "Bank", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("1300", "GST Input Credit (Unclassified)", "asset"),
    ("1301", "CGST Input Credit", "asset"), ("1302", "SGST Input Credit", "asset"),
    ("1303", "IGST Input Credit", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("2100", "GST Output Payable (Unclassified)", "liability"),
    ("2101", "CGST Output Payable", "liability"), ("2102", "SGST Output Payable", "liability"),
    ("2103", "IGST Output Payable", "liability"),
    ("2110", "TDS Payable", "liability"),
    ("3000", "Share Capital", "equity"),
    ("4000", "Sales Revenue", "income"),
    ("6000", "Operating Expenses", "expense"),
]


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    s = SessionLocal()
    org = Organization(name="T", gstin="27AAAAA0000A1Z5", state_code="27")  # Maharashtra
    s.add(org)
    s.flush()
    for code, name, atype in COA:
        s.add(Account(org_id=org.id, code=code, name=name, type=atype))
    vendor_same = Vendor(org_id=org.id, name="Same State Vendor", gstin="27BBBBB1111B1Z5")
    vendor_diff = Vendor(org_id=org.id, name="Diff State Vendor", gstin="29CCCCC2222C1Z5")
    vendor_unknown = Vendor(org_id=org.id, name="No GSTIN Vendor")
    customer_same = Customer(org_id=org.id, name="Same State Customer", gstin="27EEEEE4444E1Z5")
    customer_diff = Customer(org_id=org.id, name="Diff State Customer", gstin="19FFFFF5555F1Z5")
    s.add_all([vendor_same, vendor_diff, vendor_unknown, customer_same, customer_diff])
    s.flush()
    yield s, org, vendor_same, vendor_diff, vendor_unknown, customer_same, customer_diff
    s.rollback()
    s.close()
    Base.metadata.drop_all(engine)


def _acct_balance(s, org, code):
    a = s.query(Account).filter_by(org_id=org.id, code=code).one()
    return account_balance(s, org_id=org.id, account_id=a.id)


def test_post_bill_same_state_vendor_splits_cgst_sgst(db):
    s, org, vendor_same, *_ = db
    dist = bills.distribute(base=1000, gst_rate=18, description="consulting")
    inv, vendor, created = bills.post_bill(
        s, org_id=org.id, vendor_id=vendor_same.id, number="BILL-1",
        issue_date=date.today(), due_date=date.today() + timedelta(days=30),
        entry_mode="manual", dist=dist,
    )
    s.commit()
    assert _acct_balance(s, org, "1301") == Decimal("90.00")
    assert _acct_balance(s, org, "1302") == Decimal("90.00")
    assert _acct_balance(s, org, "1303") == Decimal("0.00")
    assert '"determination": "intra-state"' in inv.ai_meta


def test_post_bill_diff_state_vendor_posts_igst(db):
    s, org, vendor_same, vendor_diff, *_ = db
    dist = bills.distribute(base=1000, gst_rate=18, description="consulting")
    bills.post_bill(
        s, org_id=org.id, vendor_id=vendor_diff.id, number="BILL-2",
        issue_date=date.today(), due_date=date.today() + timedelta(days=30),
        entry_mode="manual", dist=dist,
    )
    s.commit()
    assert _acct_balance(s, org, "1303") == Decimal("180.00")
    assert _acct_balance(s, org, "1301") == Decimal("0.00")


def test_post_bill_unknown_state_vendor_falls_back_to_unclassified(db):
    s, org, vendor_same, vendor_diff, vendor_unknown, *_ = db
    dist = bills.distribute(base=1000, gst_rate=18, description="consulting")
    bills.post_bill(
        s, org_id=org.id, vendor_id=vendor_unknown.id, number="BILL-3",
        issue_date=date.today(), due_date=date.today() + timedelta(days=30),
        entry_mode="manual", dist=dist,
    )
    s.commit()
    assert _acct_balance(s, org, "1300") == Decimal("180.00")
    assert _acct_balance(s, org, "1301") == Decimal("0.00")


def test_post_bill_items_creates_invoice_lines_with_hsn(db):
    s, org, vendor_same, *_ = db
    inv, vendor, created, result = bills.post_bill_items(
        s, org_id=org.id, vendor_id=vendor_same.id, number="BILL-ITEM-1",
        issue_date=date.today(), due_date=date.today() + timedelta(days=30),
        entry_mode="manual", items=[{"description": "steel rods", "amount": 1000}],
    )
    s.commit()
    s.refresh(inv)
    assert len(inv.lines) == 1
    assert inv.lines[0].hsn_sac == "7214"  # Raw Material / Metal HSN
    assert _acct_balance(s, org, "1301") == Decimal("90.00")
    assert _acct_balance(s, org, "1302") == Decimal("90.00")


def test_ar_invoice_same_state_customer_splits_cgst_sgst(db):
    s, org, _vs, _vd, _vu, customer_same, _cd = db
    inv = Invoice(org_id=org.id, kind="AR", number="INV-1", customer_id=customer_same.id,
                  issue_date=date.today(), due_date=date.today() + timedelta(days=30), status="draft")
    inv.lines.append(InvoiceLine(description="Consulting", quantity=1, unit_price=1000, tax_rate=18))
    s.add(inv)
    s.flush()
    invoicing.post_invoice(s, inv)
    s.commit()
    assert _acct_balance(s, org, "2101") == Decimal("90.00")
    assert _acct_balance(s, org, "2102") == Decimal("90.00")
    assert _acct_balance(s, org, "2103") == Decimal("0.00")


def test_ar_invoice_diff_state_customer_posts_igst(db):
    s, org, _vs, _vd, _vu, _cs, customer_diff = db
    inv = Invoice(org_id=org.id, kind="AR", number="INV-2", customer_id=customer_diff.id,
                  issue_date=date.today(), due_date=date.today() + timedelta(days=30), status="draft")
    inv.lines.append(InvoiceLine(description="Consulting", quantity=1, unit_price=1000, tax_rate=18))
    s.add(inv)
    s.flush()
    invoicing.post_invoice(s, inv)
    s.commit()
    assert _acct_balance(s, org, "2103") == Decimal("180.00")
    assert _acct_balance(s, org, "2101") == Decimal("0.00")


def test_dashboard_gst_due_sums_split_accounts(db):
    s, org, vendor_same, _vd, _vu, _cs, customer_diff = db
    dist = bills.distribute(base=1000, gst_rate=18, description="consulting")
    bills.post_bill(s, org_id=org.id, vendor_id=vendor_same.id, number="BILL-A",
                    issue_date=date.today(), due_date=date.today() + timedelta(days=30),
                    entry_mode="manual", dist=dist)  # +180 input (CGST/SGST 90 each)

    inv = Invoice(org_id=org.id, kind="AR", number="INV-A", customer_id=customer_diff.id,
                  issue_date=date.today(), due_date=date.today() + timedelta(days=30), status="draft")
    inv.lines.append(InvoiceLine(description="Consulting", quantity=1, unit_price=1000, tax_rate=18))
    s.add(inv)
    s.flush()
    invoicing.post_invoice(s, inv)  # +180 output (IGST)
    s.commit()

    k = dashboard.kpis(s, org.id)
    assert k["gst_due"] == 0.0  # 180 output - 180 input


def test_distribute_preview_without_state_is_unclassified():
    """The pure preview function (no vendor resolved yet) must not guess."""
    d = bills.distribute(base=1000, gst_rate=18, description="consulting")
    assert d.gst_split.determination == "unknown"
    assert d.gst_split.unclassified == Decimal("180.00")


def test_distribute_preview_with_states_splits_correctly():
    d = bills.distribute(base=1000, gst_rate=18, description="consulting",
                         org_state="27", vendor_state="27")
    assert d.gst_split.determination == "intra-state"
    assert d.gst_split.cgst == Decimal("90.00")
