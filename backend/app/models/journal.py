from datetime import date

from sqlalchemy import ForeignKey, String, Date, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ENTRY_STATUS = ("draft", "posted", "reversed")
ENTRY_SOURCE = ("manual", "invoice", "payment", "ai", "recurring")


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = (Index("ix_je_org_date_status", "org_id", "entry_date", "status"),)

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    ref: Mapped[str] = mapped_column(String(40), default="")
    entry_date: Mapped[date] = mapped_column(Date)
    memo: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(12), default="draft")
    source: Mapped[str] = mapped_column(String(12), default="manual")
    reversed_by: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entry.id"), nullable=True
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", lazy="selectin"
    )


class JournalLine(Base):
    __tablename__ = "journal_line"
    __table_args__ = (
        Index("ix_jl_entry", "entry_id"),
        Index("ix_jl_account", "account_id"),
    )

    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entry.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    debit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    description: Mapped[str] = mapped_column(String(255), default="")

    entry: Mapped["JournalEntry"] = relationship(back_populates="lines")
