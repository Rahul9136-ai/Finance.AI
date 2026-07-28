"""Chat tool-dispatch tests — the executor must route each tool name to the
real, DB-grounded skill (or a safe error), since this is what an LLM's
tool-calling turn actually invokes."""
import os
import tempfile

import pytest

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"

from app.ai.skills import _chat_executor  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.org import Organization  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    s = SessionLocal()
    org = Organization(name="T")
    s.add(org)
    s.flush()
    yield s, org
    s.rollback()
    s.close()
    Base.metadata.drop_all(engine)


def test_get_kpis_routes_to_dashboard(db):
    s, org = db
    executor = _chat_executor(s, org.id)
    result = executor("get_kpis", {})
    assert "cash_balance" in result and "profit" in result


def test_read_invoice_routes_to_extractor(db):
    s, org = db
    executor = _chat_executor(s, org.id)
    result = executor("read_invoice", {"text": "Invoice No: INV-1 Total: 1000.00"})
    assert result["invoice_number"] == "INV-1"
    assert result["total"] == 1000.0


def test_categorize_expense_routes_correctly(db):
    s, org = db
    executor = _chat_executor(s, org.id)
    result = executor("categorize_expense", {"description": "AWS hosting bill"})
    assert result["account_code"] == "6000"


def test_score_fraud_routes_correctly(db):
    s, org = db
    executor = _chat_executor(s, org.id)
    result = executor("score_fraud", {"amount": 200000})
    assert result["risk_level"] in ("low", "medium", "high")


def test_unknown_tool_returns_error_not_exception(db):
    s, org = db
    executor = _chat_executor(s, org.id)
    result = executor("delete_everything", {})
    assert "error" in result


def test_missing_args_do_not_raise(db):
    s, org = db
    executor = _chat_executor(s, org.id)
    result = executor("categorize_expense", {})
    assert "error" not in result
    assert result["account_code"] == "6000"
