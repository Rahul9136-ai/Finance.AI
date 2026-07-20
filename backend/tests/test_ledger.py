"""Ledger integrity tests — the accounting core must never post unbalanced."""
import os
import tempfile
from datetime import date

import pytest

# Use an isolated temp SQLite DB for tests.
_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.org import Organization  # noqa: E402
from app.services.ledger import (  # noqa: E402
    LineInput, PostingError, account_balance, post_entry, reverse_entry,
)


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    s = SessionLocal()
    org = Organization(name="T")
    s.add(org)
    s.flush()
    cash = Account(org_id=org.id, code="1000", name="Cash", type="asset")
    sales = Account(org_id=org.id, code="4000", name="Sales", type="income")
    header = Account(org_id=org.id, code="9999", name="Header", type="asset",
                     is_postable=False)
    s.add_all([cash, sales, header])
    s.flush()
    yield s, org, cash, sales, header
    s.rollback()
    s.close()
    Base.metadata.drop_all(engine)


def test_balanced_entry_posts_and_updates_balances(db):
    s, org, cash, sales, _ = db
    post_entry(s, org_id=org.id, entry_date=date.today(), memo="sale",
               lines=[LineInput(cash.id, debit=1000), LineInput(sales.id, credit=1000)])
    s.commit()
    assert account_balance(s, org_id=org.id, account_id=cash.id) == 1000
    assert account_balance(s, org_id=org.id, account_id=sales.id) == 1000


def test_unbalanced_entry_rejected(db):
    s, org, cash, sales, _ = db
    with pytest.raises(PostingError):
        post_entry(s, org_id=org.id, entry_date=date.today(), memo="bad",
                   lines=[LineInput(cash.id, debit=1000), LineInput(sales.id, credit=900)])


def test_header_account_not_postable(db):
    s, org, cash, _, header = db
    with pytest.raises(PostingError):
        post_entry(s, org_id=org.id, entry_date=date.today(), memo="bad",
                   lines=[LineInput(cash.id, debit=100), LineInput(header.id, credit=100)])


def test_reversal_nets_to_zero(db):
    s, org, cash, sales, _ = db
    e = post_entry(s, org_id=org.id, entry_date=date.today(), memo="sale",
                   lines=[LineInput(cash.id, debit=1000), LineInput(sales.id, credit=1000)])
    s.commit()
    reverse_entry(s, entry=e)
    s.commit()
    assert account_balance(s, org_id=org.id, account_id=cash.id) == 0
    assert e.status == "reversed"


def test_single_line_rejected(db):
    s, org, cash, _, _ = db
    with pytest.raises(PostingError):
        post_entry(s, org_id=org.id, entry_date=date.today(), memo="bad",
                   lines=[LineInput(cash.id, debit=100)])
