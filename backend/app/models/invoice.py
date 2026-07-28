from datetime import date

from sqlalchemy import ForeignKey, String, Date, Numeric, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

INVOICE_KIND = ("AR", "AP")  # AR = customer invoice, AP = vendor bill
INVOICE_STATUS = ("draft", "open", "partial", "paid", "void")
ENTRY_MODE = ("manual", "pdf", "excel", "csv", "image", "word")  # capture method


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        Index("ix_invoice_org_kind_status", "org_id", "kind", "status", "due_date"),
    )

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    kind: Mapped[str] = mapped_column(String(2))
    number: Mapped[str] = mapped_column(String(40))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id"), nullable=True
    )
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    subtotal: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    entry_mode: Mapped[str] = mapped_column(String(10), default="manual")
    tds_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entry.id"), nullable=True
    )
    ai_meta: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_line"

    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))
    description: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[float] = mapped_column(Numeric(18, 3), default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # % GST
    hsn_sac: Mapped[str | None] = mapped_column(String(10), nullable=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("account.id"), nullable=True
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")

    @property
    def line_subtotal(self) -> float:
        return float(self.quantity) * float(self.unit_price)


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (Index("ix_payment_invoice", "invoice_id"),)

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))
    pay_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    method: Mapped[str] = mapped_column(String(20), default="bank")  # bank|upi|neft|cheque
    reference: Mapped[str] = mapped_column(String(60), default="")
    journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entry.id"), nullable=True
    )
