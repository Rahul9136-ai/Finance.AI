"""Account lookup helpers and standard-account resolution."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account

# Standard account codes the automation relies on.
#
# GST input/output each have 4 accounts: a proper CGST/SGST/IGST account per
# the place-of-supply split (see services/gst.py), plus an "unclassified"
# suspense account (the original 1300/2100 codes) used only when the
# counterparty's state can't be determined — never guessed.
STD = {
    "cash": "1000",
    "bank": "1010",
    "ar": "1100",
    "inventory": "1200",
    "fixed_assets": "1500",
    "gst_input": "1300",       # unclassified/suspense — state unknown
    "gst_input_cgst": "1301",
    "gst_input_sgst": "1302",
    "gst_input_igst": "1303",
    "ap": "2000",
    "gst_output": "2100",      # unclassified/suspense — state unknown
    "gst_output_cgst": "2101",
    "gst_output_sgst": "2102",
    "gst_output_igst": "2103",
    "tds_payable": "2110",
    "capital": "3000",
    "sales": "4000",
    "cogs": "5000",
    "opex": "6000",
}


def by_code(db: Session, org_id: int, code: str) -> Account | None:
    return db.scalar(
        select(Account).where(Account.org_id == org_id, Account.code == code)
    )


def std(db: Session, org_id: int, key: str) -> Account:
    acct = by_code(db, org_id, STD[key])
    if acct is None:
        raise ValueError(f"Standard account '{key}' ({STD[key]}) missing from COA.")
    return acct
