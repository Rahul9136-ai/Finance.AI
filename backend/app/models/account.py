from sqlalchemy import ForeignKey, String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")
# Normal balance: debit-normal types increase on the debit side.
DEBIT_NORMAL = {"asset", "expense"}


class Account(Base):
    """Chart of Accounts node."""

    __tablename__ = "account"
    __table_args__ = (Index("ix_account_org_code", "org_id", "code", unique=True),)

    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(20))  # ACCOUNT_TYPES
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"), nullable=True)
    is_postable: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def is_debit_normal(self) -> bool:
        return self.type in DEBIT_NORMAL
