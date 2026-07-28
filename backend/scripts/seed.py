"""Idempotent-ish seed: creates schema, roles, org, users, COA, and demo txns.

Run:  python -m scripts.seed
"""
from datetime import date, timedelta

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.account import Account
from app.models.invoice import Invoice, InvoiceLine
from app.models.org import Organization
from app.models.party import Customer, Vendor
from app.models.user import Role, User
from app.core.security import hash_password
from app.services.invoicing import post_invoice, record_payment, refresh_totals

# ---- Roles ----
ROLES = {
    "super_admin": "*:*",
    "cfo": ("dashboard:read,account:read,journal:read,journal:post,invoice:*,"
            "payment:*,vendor:*,customer:*,report:*,tax:*,ai:*"),
    "finance_manager": ("dashboard:read,account:read,journal:read,journal:post,"
                        "invoice:*,payment:create,payment:approve,vendor:*,"
                        "customer:*,report:read,report:export,ai:read"),
    "accountant": ("dashboard:read,account:read,journal:read,journal:create,"
                   "invoice:read,invoice:create,invoice:update,invoice:post,"
                   "payment:create,vendor:*,customer:*,report:read,ai:read"),
    "auditor": ("dashboard:read,account:read,journal:read,invoice:read,"
                "vendor:read,customer:read,report:read,report:export,ai:read"),
}

# ---- Chart of Accounts (code, name, type) ----
COA = [
    ("1000", "Cash", "asset"),
    ("1010", "Bank", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("1200", "Inventory", "asset"),
    ("1300", "GST Input Credit (Unclassified)", "asset"),
    ("1301", "CGST Input Credit", "asset"),
    ("1302", "SGST Input Credit", "asset"),
    ("1303", "IGST Input Credit", "asset"),
    ("1500", "Fixed Assets", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("2100", "GST Output Payable (Unclassified)", "liability"),
    ("2101", "CGST Output Payable", "liability"),
    ("2102", "SGST Output Payable", "liability"),
    ("2103", "IGST Output Payable", "liability"),
    ("2110", "TDS Payable", "liability"),
    ("3000", "Share Capital", "equity"),
    ("4000", "Sales Revenue", "income"),
    ("5000", "Cost of Goods Sold", "expense"),
    ("6000", "Operating Expenses", "expense"),
    ("6100", "Rent", "expense"),
    ("6200", "Salaries", "expense"),
    ("6300", "Stationery & Printing", "expense"),
    ("6400", "IT, Software & Subscriptions", "expense"),
    ("6500", "Travel & Conveyance", "expense"),
    ("6600", "Utilities", "expense"),
    ("6700", "Professional & Legal Fees", "expense"),
    ("6800", "Repairs & Maintenance", "expense"),
    ("6900", "Freight & Logistics", "expense"),
]

USERS = [
    ("admin@demo.io", "Ada Admin", "super_admin"),
    ("cfo@demo.io", "Chris CFO", "cfo"),
    ("manager@demo.io", "Meera Manager", "finance_manager"),
    ("accountant@demo.io", "Amit Accountant", "accountant"),
    ("auditor@demo.io", "Ravi Auditor", "auditor"),
]


def get_or_create(db, model, defaults=None, **kw):
    obj = db.scalar(select(model).filter_by(**kw))
    if obj:
        return obj, False
    obj = model(**kw, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj, True


def run():
    Base.metadata.create_all(engine)
    db = SessionLocal()

    roles = {}
    for name, perms in ROLES.items():
        r, _ = get_or_create(db, Role, name=name, defaults={"permissions": perms})
        r.permissions = perms
        roles[name] = r

    org, _ = get_or_create(
        db, Organization, name="Demo Manufacturing Pvt Ltd",
        defaults={"country": "IN", "base_currency": "INR", "gstin": "27AAAAA0000A1Z5",
                  "state_code": "27"},  # Maharashtra
    )

    for email, full_name, role_name in USERS:
        u, created = get_or_create(
            db, User, email=email,
            defaults={"org_id": org.id, "role_id": roles[role_name].id,
                      "full_name": full_name,
                      "hashed_password": hash_password("demo1234"),
                      "must_change_password": False},
        )
        u.role_id = roles[role_name].id
        u.must_change_password = False

    for code, name, atype in COA:
        get_or_create(db, Account, org_id=org.id, code=code,
                      defaults={"name": name, "type": atype})

    db.flush()

    # ---- Demo master data (only if none yet) ----
    if not db.scalar(select(Vendor).where(Vendor.org_id == org.id)):
        for n, g in [("Steel Supplies Co", "27BBBBB1111B1Z5"),
                     ("CloudHost Ltd", "29CCCCC2222C1Z5"),
                     ("Office Rentals LLP", "27DDDDD3333D1Z5")]:
            db.add(Vendor(org_id=org.id, name=n, gstin=g, ai_score=72))
    if not db.scalar(select(Customer).where(Customer.org_id == org.id)):
        # Acme (same state as org -> CGST+SGST), BlueMart (different state ->
        # IGST), Zeta (no GSTIN/state on file -> demonstrates the unclassified
        # suspense-account fallback until their state is captured).
        for n, cl, g in [("Acme Retail", 500000, "27EEEEE4444E1Z5"),
                         ("BlueMart", 250000, "19FFFFF5555F1Z5"),
                         ("Zeta Traders", 100000, None)]:
            db.add(Customer(org_id=org.id, name=n, credit_limit=cl, gstin=g))
    db.flush()

    vendors = db.scalars(select(Vendor).where(Vendor.org_id == org.id)).all()
    customers = db.scalars(select(Customer).where(Customer.org_id == org.id)).all()

    # ---- Demo transactions (only seed once) ----
    existing = db.scalar(select(Invoice).where(Invoice.org_id == org.id))
    if not existing:
        today = date.today()

        # Opening capital injection: Dr Bank / Cr Share Capital
        from app.services import accounts as _acct
        from app.services.ledger import LineInput, post_entry
        post_entry(
            db, org_id=org.id, entry_date=today - timedelta(days=60),
            memo="Opening share capital",
            lines=[LineInput(_acct.std(db, org.id, "bank").id, debit=1000000),
                   LineInput(_acct.std(db, org.id, "capital").id, credit=1000000)],
            source="manual", ref="OPEN-CAP",
        )

        def mk_invoice(kind, number, party, days_ago, due_in, lines):
            inv = Invoice(
                org_id=org.id, kind=kind, number=number,
                vendor_id=party.id if kind == "AP" else None,
                customer_id=party.id if kind == "AR" else None,
                issue_date=today - timedelta(days=days_ago),
                due_date=today - timedelta(days=days_ago) + timedelta(days=due_in),
                status="draft",
            )
            for desc, qty, price, tax in lines:
                inv.lines.append(InvoiceLine(description=desc, quantity=qty,
                                             unit_price=price, tax_rate=tax))
            refresh_totals(inv)
            db.add(inv)
            db.flush()
            post_invoice(db, inv)
            return inv

        # AR — customer sales
        ar1 = mk_invoice("AR", "INV-1001", customers[0], 40, 30,
                         [("Widget Model A", 100, 500, 18)])
        mk_invoice("AR", "INV-1002", customers[1], 20, 30,
                   [("Widget Model B", 50, 800, 18)])
        ar3 = mk_invoice("AR", "INV-1003", customers[2], 5, 30,
                         [("Consulting", 10, 2000, 18)])
        # AP — vendor bills
        ap1 = mk_invoice("AP", "BILL-2001", vendors[0], 35, 30,
                         [("Raw steel", 200, 300, 18)])
        mk_invoice("AP", "BILL-2002", vendors[1], 15, 15,
                   [("Cloud hosting", 1, 40000, 18)])
        mk_invoice("AP", "BILL-2003", vendors[2], 3, 7,
                   [("Office rent", 1, 60000, 0)])

        # Some settlements so cash/bank has movement
        record_payment(db, ar1, amount=float(ar1.total), pay_date=today - timedelta(days=8),
                       method="neft", reference="RCPT-9001")
        record_payment(db, ar3, amount=float(ar3.total) / 2, pay_date=today - timedelta(days=1),
                       method="upi", reference="RCPT-9002")
        record_payment(db, ap1, amount=float(ap1.total), pay_date=today - timedelta(days=5),
                       method="neft", reference="PAY-8001")

    db.commit()

    print("\n[OK] Seed complete.")
    print(f"   Org: {org.name} (id={org.id})")
    print("   Login with password 'demo1234':")
    for email, _, role_name in USERS:
        print(f"     - {email:22s} [{role_name}]")
    db.close()


if __name__ == "__main__":
    run()
